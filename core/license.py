"""License validation for CutPilot.

Simple HMAC-based activation codes with machine binding and expiry.
Code format: CP-{expiry_YYYYMMDD}-{machine_hash[:8]}-{hmac[:12]}
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import platform
import uuid
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_LICENSE_DIR = Path.home() / ".cutpilot"
_LICENSE_PATH = _LICENSE_DIR / "license.json"

# Obfuscated — not truly secure, just a deterrent for casual copying
_SECRET = b"CutPilot-2026-v1-license-key-do-not-share"

_MAX_TRIAL_USES = 3


def get_machine_id() -> str:
    """Generate a stable machine identifier."""
    raw = f"{platform.node()}-{uuid.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def generate_activation_code(machine_id: str, expiry: date) -> str:
    """Generate an activation code (admin use only).

    Args:
        machine_id: Target machine's ID from get_machine_id().
        expiry: Expiration date.

    Returns:
        Activation code string: CP-YYYYMMDD-{machine[:8]}-{hmac[:12]}
    """
    expiry_str = expiry.strftime("%Y%m%d")
    payload = f"{machine_id}:{expiry_str}"
    sig = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:12]
    return f"CP-{expiry_str}-{machine_id[:8]}-{sig}"


def validate_activation_code(code: str) -> tuple[bool, str]:
    """Validate an activation code against this machine.

    Returns:
        (is_valid, message)
    """
    parts = code.strip().split("-")
    if len(parts) != 4 or parts[0] != "CP":
        return False, "激活码格式无效"

    expiry_str = parts[1]
    code_machine = parts[2]
    code_sig = parts[3]

    # Validate expiry date format
    try:
        expiry = datetime.strptime(expiry_str, "%Y%m%d").date()
    except ValueError:
        return False, "激活码日期格式无效"

    # Check expiry
    if expiry < date.today():
        return False, f"激活码已过期 ({expiry.isoformat()})"

    # Verify machine binding
    machine_id = get_machine_id()
    if machine_id[:8] != code_machine:
        return False, "激活码与本机不匹配"

    # Recompute HMAC and compare
    payload = f"{machine_id}:{expiry_str}"
    expected_sig = hmac.new(
        _SECRET, payload.encode(), hashlib.sha256,
    ).hexdigest()[:12]

    if not hmac.compare_digest(code_sig, expected_sig):
        return False, "激活码签名无效"

    return True, f"激活码有效，到期日: {expiry.isoformat()}"


def activate(code: str) -> tuple[bool, str]:
    """Validate and save activation code.

    Returns:
        (success, message)
    """
    valid, message = validate_activation_code(code)
    if not valid:
        return False, message

    parts = code.strip().split("-")
    expiry_str = parts[1]

    license_data = _read_license_file()
    updated = {
        **license_data,
        "activation_code": code.strip(),
        "expiry": expiry_str,
        "machine_id": get_machine_id(),
        "activated_at": datetime.now().isoformat(),
    }
    _write_license_file(updated)

    logger.info("License activated, expiry: %s", expiry_str)
    return True, "激活成功！"


def check_license() -> tuple[bool, str, date | None]:
    """Check if a valid license exists.

    Returns:
        (is_valid, message, expiry_date_or_none)
    """
    license_data = _read_license_file()
    code = license_data.get("activation_code")
    if not code:
        return False, "未激活", None

    valid, message = validate_activation_code(code)
    if not valid:
        return False, message, None

    expiry_str = license_data.get("expiry", "")
    try:
        expiry = datetime.strptime(expiry_str, "%Y%m%d").date()
    except ValueError:
        return False, "许可证日期损坏", None

    return True, f"有效，到期: {expiry.isoformat()}", expiry


def get_license_info() -> dict:
    """Return current license info for UI display."""
    license_data = _read_license_file()
    is_valid, message, expiry = check_license()

    trial_remaining = _MAX_TRIAL_USES - license_data.get("trial_uses", 0)
    trial_remaining = max(0, trial_remaining)

    return {
        "machine_id": get_machine_id(),
        "is_valid": is_valid,
        "status_message": message,
        "expiry": expiry.isoformat() if expiry else None,
        "trial_remaining": trial_remaining,
        "activation_code": license_data.get("activation_code", ""),
    }


def get_trial_remaining() -> int:
    """Return the number of trial uses remaining."""
    license_data = _read_license_file()
    used = license_data.get("trial_uses", 0)
    return max(0, _MAX_TRIAL_USES - used)


def consume_trial() -> tuple[bool, int]:
    """Consume one trial use. Returns (success, remaining)."""
    license_data = _read_license_file()
    used = license_data.get("trial_uses", 0)
    remaining = _MAX_TRIAL_USES - used

    if remaining <= 0:
        return False, 0

    updated = {**license_data, "trial_uses": used + 1}
    _write_license_file(updated)

    new_remaining = remaining - 1
    logger.info("Trial use consumed, remaining: %d", new_remaining)
    return True, new_remaining


# ── Internal helpers ──


def _read_license_file() -> dict:
    """Read the license JSON file, returning empty dict on failure."""
    if not _LICENSE_PATH.exists():
        return {}
    try:
        raw = _LICENSE_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read license file: %s", exc)
        return {}


def _write_license_file(data: dict) -> None:
    """Write license data to JSON file."""
    _LICENSE_DIR.mkdir(parents=True, exist_ok=True)
    _LICENSE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
