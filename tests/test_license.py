"""Tests for core.license — activation, expiry, HMAC tampering, repeat activation."""
import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from core.license import (
    activate,
    check_license,
    consume_trial,
    generate_activation_code,
    get_license_info,
    get_machine_id,
    get_trial_remaining,
    validate_activation_code,
)


# -- Fixtures ----------------------------------------------------------------


FAKE_MACHINE_ID = "abcdef1234567890"


@pytest.fixture(autouse=True)
def _isolate_license(tmp_path):
    """Redirect license file to tmp_path so tests never touch real license."""
    license_path = tmp_path / "license.json"
    with (
        patch("core.license._LICENSE_DIR", tmp_path),
        patch("core.license._LICENSE_PATH", license_path),
        patch("core.license.get_machine_id", return_value=FAKE_MACHINE_ID),
    ):
        yield


# -- generate / validate round-trip ------------------------------------------


class TestGenerateAndValidate:
    def test_valid_code_passes(self):
        expiry = date.today() + timedelta(days=30)
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)
        valid, msg = validate_activation_code(code)
        assert valid is True
        assert "有效" in msg

    def test_format_structure(self):
        expiry = date.today() + timedelta(days=30)
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)
        parts = code.split("-")
        assert len(parts) == 4
        assert parts[0] == "CP"
        assert parts[2] == FAKE_MACHINE_ID[:8]


# -- Expiry ------------------------------------------------------------------


class TestExpiry:
    def test_expired_code_rejected(self):
        expiry = date.today() - timedelta(days=1)
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)
        valid, msg = validate_activation_code(code)
        assert valid is False
        assert "过期" in msg

    def test_expires_today_is_valid(self):
        expiry = date.today()
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)
        valid, msg = validate_activation_code(code)
        assert valid is True

    def test_far_future_is_valid(self):
        expiry = date.today() + timedelta(days=3650)
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)
        valid, msg = validate_activation_code(code)
        assert valid is True


# -- HMAC tampering ----------------------------------------------------------


class TestHmacTampering:
    def test_tampered_signature_rejected(self):
        expiry = date.today() + timedelta(days=30)
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)
        parts = code.split("-")
        parts[3] = "000000000000"  # forged signature
        tampered = "-".join(parts)
        valid, msg = validate_activation_code(tampered)
        assert valid is False
        assert "签名无效" in msg

    def test_tampered_expiry_rejected(self):
        """Changing the expiry date invalidates the HMAC."""
        expiry = date.today() + timedelta(days=30)
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)
        parts = code.split("-")
        # Push expiry forward by a year
        new_expiry = date.today() + timedelta(days=365)
        parts[1] = new_expiry.strftime("%Y%m%d")
        tampered = "-".join(parts)
        valid, msg = validate_activation_code(tampered)
        assert valid is False
        assert "签名无效" in msg

    def test_invalid_format_rejected(self):
        valid, msg = validate_activation_code("NOT-A-REAL-CODE-AT-ALL")
        assert valid is False
        assert "格式无效" in msg

    def test_garbage_date_rejected(self):
        valid, msg = validate_activation_code("CP-99999999-abcdef12-aabbccddeeff")
        assert valid is False
        # Either date format or signature error
        assert not valid


# -- Machine binding ---------------------------------------------------------


class TestMachineBinding:
    def test_wrong_machine_rejected(self):
        expiry = date.today() + timedelta(days=30)
        other_machine = "ffffffffffffffff"
        code = generate_activation_code(other_machine, expiry)
        valid, msg = validate_activation_code(code)
        assert valid is False
        assert "不匹配" in msg


# -- Repeat activation (same machine) ---------------------------------------


class TestRepeatActivation:
    def test_activate_twice_succeeds(self):
        """Same machine activating twice should overwrite, not fail."""
        expiry = date.today() + timedelta(days=30)
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)

        ok1, _ = activate(code)
        assert ok1 is True

        ok2, _ = activate(code)
        assert ok2 is True

    def test_activate_then_check(self):
        expiry = date.today() + timedelta(days=30)
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)

        activate(code)
        valid, msg, exp = check_license()
        assert valid is True
        assert exp == expiry

    def test_activate_new_code_replaces_old(self):
        expiry1 = date.today() + timedelta(days=10)
        expiry2 = date.today() + timedelta(days=90)
        code1 = generate_activation_code(FAKE_MACHINE_ID, expiry1)
        code2 = generate_activation_code(FAKE_MACHINE_ID, expiry2)

        activate(code1)
        activate(code2)
        valid, msg, exp = check_license()
        assert valid is True
        assert exp == expiry2


# -- Offline verification (no network needed) --------------------------------


class TestOfflineVerification:
    def test_validate_is_purely_local(self):
        """Validation uses only HMAC — no HTTP calls should be made."""
        expiry = date.today() + timedelta(days=30)
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)

        # Patch socket to raise if anything tries to connect
        import socket
        original_connect = socket.socket.connect

        def block_connect(*args, **kwargs):
            raise AssertionError("Network call detected during validation!")

        with patch.object(socket.socket, "connect", block_connect):
            valid, msg = validate_activation_code(code)
            assert valid is True

    def test_check_license_offline(self):
        """check_license reads from disk, no network."""
        expiry = date.today() + timedelta(days=30)
        code = generate_activation_code(FAKE_MACHINE_ID, expiry)
        activate(code)

        import socket
        with patch.object(
            socket.socket, "connect",
            side_effect=AssertionError("No network!"),
        ):
            valid, msg, exp = check_license()
            assert valid is True


# -- Trial uses --------------------------------------------------------------


class TestTrialUses:
    def test_initial_remaining_is_3(self):
        assert get_trial_remaining() == 3

    def test_consume_decrements(self):
        ok, remaining = consume_trial()
        assert ok is True
        assert remaining == 2

    def test_consume_exhausted(self):
        for _ in range(3):
            consume_trial()
        ok, remaining = consume_trial()
        assert ok is False
        assert remaining == 0

    def test_license_info_shows_trial(self):
        consume_trial()
        info = get_license_info()
        assert info["trial_remaining"] == 2
        assert info["machine_id"] == FAKE_MACHINE_ID


# -- Edge: corrupted license file -------------------------------------------


class TestCorruptedLicenseFile:
    def test_corrupted_json_returns_invalid(self, tmp_path):
        license_path = tmp_path / "license.json"
        license_path.write_text("NOT JSON!!!", encoding="utf-8")
        valid, msg, exp = check_license()
        assert valid is False

    def test_empty_file_returns_invalid(self, tmp_path):
        license_path = tmp_path / "license.json"
        license_path.write_text("", encoding="utf-8")
        valid, msg, exp = check_license()
        assert valid is False
