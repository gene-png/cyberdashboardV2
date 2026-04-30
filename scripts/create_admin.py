#!/usr/bin/env python3
"""
Generate a bcrypt hash for use as the ADMIN_PASSWORD_HASH environment variable.

Usage:
    python scripts/create_admin.py
    python scripts/create_admin.py --password mysecretpassword

Set the output as the ADMIN_PASSWORD_HASH env var in your App Service configuration.
"""
import argparse
import getpass
import sys


def main():
    parser = argparse.ArgumentParser(description="Generate admin password hash")
    parser.add_argument("--password", help="Password to hash (prompted if omitted)")
    args = parser.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass("Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.", file=sys.stderr)
            sys.exit(1)

    if len(password) < 12:
        print("Warning: password is shorter than 12 characters.", file=sys.stderr)

    try:
        from werkzeug.security import generate_password_hash
    except ImportError:
        print("werkzeug is not installed. Run: pip install werkzeug", file=sys.stderr)
        sys.exit(1)

    hashed = generate_password_hash(password)
    print(f"\nADMIN_PASSWORD_HASH={hashed}\n")
    print("Set this as an environment variable (App Service → Configuration → Application settings).")


if __name__ == "__main__":
    main()
