"""Check that this machine (or the EC2 instance) can reach the AWS services QuickBite needs.

Usage (on EC2, inside the venv):  python scripts/test_aws_connection.py
It prints PASS/FAIL for each check. It never prints credentials.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import boto3  # noqa: E402
from botocore.exceptions import BotoCoreError, ClientError  # noqa: E402

from config import Config  # noqa: E402


def check(label, fn):
    try:
        detail = fn()
        print(f"[PASS] {label}" + (f" - {detail}" if detail else ""))
        return True
    except (BotoCoreError, ClientError) as exc:
        print(f"[FAIL] {label} - {exc.__class__.__name__}: {getattr(exc, 'response', {}).get('Error', {}).get('Code', '')}")
        return False


def main():
    region = Config.AWS_REGION
    print(f"Region: {region}   APP_MODE: {Config.APP_MODE}")
    results = []

    results.append(check("STS: caller identity (shows the IAM role ARN, no keys)",
                         lambda: boto3.client("sts", region_name=region).get_caller_identity()["Arn"]))

    dynamo = boto3.client("dynamodb", region_name=region)
    for table in (Config.MENU_TABLE_NAME, Config.ORDERS_TABLE_NAME, Config.STUDENTS_TABLE_NAME):
        results.append(check(f"DynamoDB table exists: {table}",
                             lambda t=table: dynamo.describe_table(TableName=t)["Table"]["TableStatus"]))

    results.append(check("DynamoDB: menu table can be read",
                         lambda: f"{len(boto3.resource('dynamodb', region_name=region).Table(Config.MENU_TABLE_NAME).scan(Limit=50).get('Items', []))} item(s) returned"))

    # SMS test is opt-in because it sends a real text message and may cost money.
    # Usage: python scripts/test_aws_connection.py --sms-test +919876543210
    if "--sms-test" in sys.argv:
        phone = sys.argv[sys.argv.index("--sms-test") + 1]
        results.append(check(
            "SNS: test SMS accepted (accepted means SNS took the request, not handset delivery)",
            lambda: boto3.client("sns", region_name=region).publish(
                PhoneNumber=phone, Message="QuickBite connectivity test. You can ignore this message.")["MessageId"],
        ))
    else:
        print("[SKIP] SNS test SMS (add --sms-test +91XXXXXXXXXX to send one)")

    print("\nAll checks passed." if all(results) else "\nSome checks failed. See docs/troubleshooting.md.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
