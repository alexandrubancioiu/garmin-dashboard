"""Log in to Garmin Connect once and save the session tokens.

Usage:
    python garmin_login.py [--force]

Asks for the Garmin Connect email, password and, if the account uses two-step
verification, the code Garmin sends by email or SMS. The password is never
stored: only the session tokens are saved, in ~/.garminconnect (or the folder
in the GARMINTOKENS environment variable). They last about 6 months; run this
again with --force when the export starts failing to log in.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

from garminconnect import Garmin

TOKENS = os.environ.get("GARMINTOKENS", str(Path.home() / ".garminconnect"))


def tokens_work(path):
    """True and the account name if the saved tokens still log in."""
    try:
        api = Garmin()
        api.login(path)
        return True, api.get_full_name()
    except Exception as exc:  # any failure means a fresh login is needed
        return False, str(exc)


def secure(path):
    """Owner-only permissions on the token folder (they give full account access)."""
    try:
        os.chmod(path, 0o700)
        for entry in os.scandir(path):
            if entry.is_file():
                os.chmod(entry.path, 0o600)
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Log in to Garmin Connect for garmin-dashboard.")
    parser.add_argument("--force", action="store_true", help="log in again even if saved tokens exist")
    args = parser.parse_args()

    if not args.force and Path(TOKENS).exists():
        ok, who = tokens_work(TOKENS)
        if ok:
            print(f"Already logged in as {who}. Use --force to log in again.")
            return 0
        print("The saved tokens no longer work; logging in again.\n")

    email = input("Garmin Connect email: ").strip()
    password = getpass.getpass("Password (hidden while you type): ")
    if not email or not password:
        print("Email and password are both required.", file=sys.stderr)
        return 1

    print("\nLogging in to Garmin Connect...")
    try:
        api = Garmin(email=email, password=password, return_on_mfa=True)
        first, state = api.client.login(email, password, return_on_mfa=True)
        if first == "needs_mfa":
            code = input("Code from Garmin (email or SMS): ").strip()
            api.resume_login(state, code)
        api.client.dump(TOKENS)
        secure(TOKENS)
    except Exception as exc:
        text = str(exc)
        print(f"\nLogin failed: {text}", file=sys.stderr)
        if "429" in text:
            print("Garmin is rate limiting login attempts. Wait 15-30 minutes and try again.", file=sys.stderr)
        else:
            print("Check your email and password, then try again.", file=sys.stderr)
        return 1

    ok, who = tokens_work(TOKENS)
    if not ok:
        print(f"\nThe tokens were saved, but reading the account failed: {who}", file=sys.stderr)
        print("Wait a few minutes and run again with --force.", file=sys.stderr)
        return 1
    print(f"\nLogged in as {who}. The tokens are in {TOKENS} and last about 6 months.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
