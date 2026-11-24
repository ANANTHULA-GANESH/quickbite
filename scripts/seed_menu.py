"""Load the sample menu into the active backend.

Usage (from the project folder):
    python scripts/seed_menu.py

APP_MODE=demo -> writes to the local SQLite file.
APP_MODE=aws  -> writes to the DynamoDB MenuItems table (needs AWS credentials for your
                 laptop with dynamodb:PutItem, for example from `aws configure`).
Running it twice is safe: existing items with the same item_id are replaced.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import Config  # noqa: E402
from services.menu_data import SAMPLE_MENU  # noqa: E402


def main():
    if Config.APP_MODE == "aws":
        from services.dynamodb_service import DynamoStore

        store = DynamoStore(
            Config.AWS_REGION, Config.MENU_TABLE_NAME, Config.ORDERS_TABLE_NAME, Config.ORDERS_DATE_INDEX
        )
    else:
        from services.demo_store import DemoStore

        store = DemoStore(Config.DEMO_DB_PATH)

    store.upsert_menu_items(SAMPLE_MENU)
    print(f"Seeded {len(SAMPLE_MENU)} menu items (APP_MODE={Config.APP_MODE}).")


if __name__ == "__main__":
    main()
