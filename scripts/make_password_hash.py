"""Create a password hash for the staff login.

Usage:  python scripts/make_password_hash.py
The plain password is typed in privately (it is not echoed) and is never saved anywhere.
Copy the printed STAFF_PASSWORD_HASH line into your environment file.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash  # noqa: E402


def main():
    password = getpass.getpass("New staff password: ")
    confirm = getpass.getpass("Repeat password: ")
    if password != confirm:
        print("Passwords do not match.")
        return 1
    if len(password) < 10:
        print("Use at least 10 characters.")
        return 1

    # Werkzeug uses salted scrypt by default.
    password_hash = generate_password_hash(password)
    print("\nAdd this line to your environment file (.env or /etc/quickbite/quickbite.env):\n")
    print(f"STAFF_PASSWORD_HASH='{password_hash}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
