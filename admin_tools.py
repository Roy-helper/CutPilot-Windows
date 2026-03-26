#!/usr/bin/env python3
"""CutPilot 管理员工具 — 生成激活码、管理测试用户。

用法:
    # 查看本机机器码
    python admin_tools.py machine-id

    # 为指定机器码生成 30 天激活码
    python admin_tools.py gen <machine_id> --days 30

    # 批量生成（测试人员把机器码发给你，你批量生成）
    python admin_tools.py batch machines.txt --days 30
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path


def cmd_machine_id():
    from core.license import get_machine_id
    mid = get_machine_id()
    print(f"本机机器码: {mid}")
    print(f"复制前 8 位: {mid[:8]}")


def cmd_generate(machine_id: str, days: int):
    from core.license import generate_activation_code
    expiry = date.today() + timedelta(days=days)
    code = generate_activation_code(machine_id, expiry)
    print(f"机器码:   {machine_id[:8]}...")
    print(f"有效期:   {expiry.isoformat()} ({days} 天)")
    print(f"激活码:   {code}")
    print()
    print(f"发给测试人员的消息:")
    print(f"---")
    print(f"你的 CutPilot 激活码: {code}")
    print(f"有效期至: {expiry.isoformat()}")
    print(f"打开 CutPilot → 设置 → 授权详情 → 输入激活码")
    print(f"---")


def cmd_batch(file_path: str, days: int):
    from core.license import generate_activation_code
    expiry = date.today() + timedelta(days=days)
    lines = Path(file_path).read_text().strip().splitlines()
    print(f"批量生成 {len(lines)} 个激活码 (有效期 {days} 天，到 {expiry.isoformat()})")
    print()
    for line in lines:
        parts = line.strip().split()
        machine_id = parts[0]
        name = parts[1] if len(parts) > 1 else "未知"
        code = generate_activation_code(machine_id, expiry)
        print(f"{name:<12} {machine_id[:8]}...  →  {code}")


def cmd_activate_local(code: str):
    from core.license import activate
    ok, msg = activate(code)
    print(f"{'成功' if ok else '失败'}: {msg}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "machine-id":
        cmd_machine_id()
    elif cmd == "gen":
        if len(sys.argv) < 3:
            print("用法: python admin_tools.py gen <machine_id> [--days 30]")
            sys.exit(1)
        mid = sys.argv[2]
        days = 30
        if "--days" in sys.argv:
            idx = sys.argv.index("--days")
            days = int(sys.argv[idx + 1])
        cmd_generate(mid, days)
    elif cmd == "batch":
        if len(sys.argv) < 3:
            print("用法: python admin_tools.py batch machines.txt [--days 30]")
            sys.exit(1)
        days = 30
        if "--days" in sys.argv:
            idx = sys.argv.index("--days")
            days = int(sys.argv[idx + 1])
        cmd_batch(sys.argv[2], days)
    elif cmd == "activate":
        if len(sys.argv) < 3:
            print("用法: python admin_tools.py activate <激活码>")
            sys.exit(1)
        cmd_activate_local(sys.argv[2])
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
