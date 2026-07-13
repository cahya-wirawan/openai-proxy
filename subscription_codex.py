#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import webbrowser

from openai_codex import Codex


def login(device_code: bool) -> int:
    with Codex() as codex:
        if device_code:
            handle = codex.login_chatgpt_device_code()
            print(f"Open: {handle.verification_url}")
            print(f"Code: {handle.user_code}")
        else:
            handle = codex.login_chatgpt()
            print(f"Open: {handle.auth_url}")
            webbrowser.open(handle.auth_url)

        result = handle.wait()
        if not result.success:
            print(f"Login failed: {result}", file=sys.stderr)
            return 1

        print("ChatGPT/Codex login successful.")
        return 0


def account() -> int:
    with Codex() as codex:
        print(codex.account(refresh_token=True))
    return 0


def logout() -> int:
    with Codex() as codex:
        codex.logout()
    print("Codex credentials cleared.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    login_parser = sub.add_parser("login")
    login_parser.add_argument("--device-code", action="store_true")
    sub.add_parser("account")
    sub.add_parser("logout")

    args = parser.parse_args()
    if args.command == "login":
        return login(args.device_code)
    if args.command == "account":
        return account()
    if args.command == "logout":
        return logout()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
