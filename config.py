"""Application settings.

Every value comes from an environment variable (or a .env file during development).
No AWS access keys belong here. On EC2 the instance role provides AWS permissions.
"""
import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # "demo" = local SQLite file, no AWS calls.  "aws" = DynamoDB (and SNS if enabled).
    APP_MODE = os.environ.get("APP_MODE", "demo").strip().lower()

    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    # Hash created by scripts/make_password_hash.py. The plain password is never stored.
    STAFF_PASSWORD_HASH = os.environ.get("STAFF_PASSWORD_HASH", "")
    STAFF_SESSION_HOURS = int(os.environ.get("STAFF_SESSION_HOURS", "8"))
    TIMEZONE = os.environ.get("TIMEZONE", "Asia/Kolkata")

    AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
    MENU_TABLE_NAME = os.environ.get("MENU_TABLE_NAME", "QuickBite-MenuItems")
    ORDERS_TABLE_NAME = os.environ.get("ORDERS_TABLE_NAME", "QuickBite-Orders")
    STUDENTS_TABLE_NAME = os.environ.get("STUDENTS_TABLE_NAME", "QuickBite-Students")
    ORDERS_DATE_INDEX = "ByOrderDate"
    ORDERS_USER_INDEX = "ByStudentPhone"

    SNS_ENABLED = _env_bool("SNS_ENABLED", False)
    SNS_SMS_SENDER_ID = os.environ.get("SNS_SMS_SENDER_ID", "")

    DEMO_DB_PATH = os.environ.get(
        "DEMO_DB_PATH", os.path.join(BASE_DIR, "instance", "quickbite_demo.db")
    )

    MAX_CART_LINES = 30
    MAX_QUANTITY = 10

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
