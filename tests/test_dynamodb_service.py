"""Tests for the DynamoDB storage layer against a mocked AWS (moto). No real AWS account is used.

The table definitions match infrastructure/cloudformation/quickbite-stack.yaml.
"""
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import boto3
import pytest

moto = pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

from services.dynamodb_service import DynamoStore  # noqa: E402
from services.errors import ConflictError, DuplicateStudentError, NotFoundError  # noqa: E402
from services.menu_data import SAMPLE_MENU  # noqa: E402
from services.order_service import OrderService  # noqa: E402

REGION = "ap-south-1"
MENU_TABLE = "QuickBite-MenuItems"
ORDERS_TABLE = "QuickBite-Orders"
STUDENTS_TABLE = "QuickBite-Students"


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        client.create_table(
            TableName=MENU_TABLE,
            AttributeDefinitions=[{"AttributeName": "item_id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "item_id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName=ORDERS_TABLE,
            AttributeDefinitions=[
                {"AttributeName": "order_id", "AttributeType": "S"},
                {"AttributeName": "order_date", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
                {"AttributeName": "student_phone", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            GlobalSecondaryIndexes=[{
                "IndexName": "ByOrderDate",
                "KeySchema": [
                    {"AttributeName": "order_date", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }, {
                "IndexName": "ByStudentPhone",
                "KeySchema": [
                    {"AttributeName": "student_phone", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName=STUDENTS_TABLE,
            AttributeDefinitions=[{"AttributeName": "lookup_key", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "lookup_key", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        store = DynamoStore(REGION, MENU_TABLE, ORDERS_TABLE, "ByOrderDate", STUDENTS_TABLE)
        store.upsert_menu_items(SAMPLE_MENU)
        yield store


@pytest.fixture
def service(aws):
    notifier = MagicMock()
    notifier.send.return_value = "accepted"
    return OrderService(aws, notifier, ZoneInfo("Asia/Kolkata"), 30, 10)


def test_menu_round_trip_returns_plain_numbers(aws):
    menu = aws.list_menu()
    assert len(menu) == len(SAMPLE_MENU)
    tea = next(i for i in menu if i["name"] == "Tea")
    assert tea["price"] == 15 and isinstance(tea["price"], int)


def test_place_order_writes_to_dynamodb_and_reads_back(service, aws):
    order, notification = service.place_order({
        "customer": {"student_name": "Ravi Kumar", "student_phone": "9123456780", "student_id": ""},
        "items": [{"item_id": "M007", "quantity": 1}, {"item_id": "M011", "quantity": 2}],
    })
    assert notification == "accepted"
    stored = aws.get_order(order["order_id"])
    assert stored["total_amount"] == 120 + 30
    assert stored["status"] == "Placed"
    assert stored["user_id"] == "+919123456780"
    assert stored["payment_status"] == "pay_at_pickup"
    assert stored["student_phone"] == "+919123456780"


def test_staff_listing_uses_date_index(service, aws):
    service.place_order({
        "customer": {"student_name": "Ananya Iyer", "student_phone": "9000000001", "student_id": "A1"},
        "items": [{"item_id": "M001", "quantity": 1}],
    })
    today = service.now().strftime("%Y-%m-%d")
    result = service.list_staff_orders(order_date=today)
    assert result["counts"]["Total"] == 1
    assert result["orders"][0]["student_name"] == "Ananya Iyer"


def test_conditional_status_update_rejects_stale_writes(service, aws):
    order, _ = service.place_order({
        "customer": {"student_name": "Dev Patel", "student_phone": "9000000002", "student_id": ""},
        "items": [{"item_id": "M012", "quantity": 1}],
    })
    service.update_status(order["order_id"], "Preparing")
    # A second writer still believes the order is Pending. The conditional write must refuse.
    assert aws.update_status(order["order_id"], "Pending", "Preparing", "2026-01-01T00:00:00+05:30") is False
    assert aws.get_order(order["order_id"])["status"] == "Preparing"


def test_unknown_order_status_update_raises_not_found(service):
    with pytest.raises(NotFoundError):
        service.update_status("QB-2026-DEADBEEF", "Preparing")


def test_update_on_missing_item_does_not_create_it(aws):
    # attribute_exists in the condition prevents update_item from creating a ghost order.
    assert aws.update_status("QB-2026-00000001", "Pending", "Preparing", "x") is False
    assert aws.get_order("QB-2026-00000001") is None


def test_student_account_and_menu_management_round_trip(aws):
    student = {"name": "Ravi Kumar", "phone": "9123456780", "student_id": "1234567890"}
    aws.create_student(student)
    assert aws.get_student_by_phone(student["phone"]) == student

    item = {
        "item_id": "M-NEW", "name": "New Tea", "category": "Beverages", "price": 20,
        "emoji": "🍽️", "description": "", "image_url": "", "available": True, "featured": False,
    }
    aws.add_menu_item(item)
    updated = aws.update_menu_item(item["item_id"], {"name": "Masala Tea", "available": False})
    assert updated["name"] == "Masala Tea"
    assert updated["available"] is False
    with pytest.raises(DuplicateStudentError) as exc_info:
        aws.create_student({**student, "name": "Duplicate"})
    assert "phone number already exists" in str(exc_info.value)


def test_dynamo_student_id_is_unique(aws):
    aws.create_student({"name": "Ravi Kumar", "phone": "9123456780", "student_id": "1234567890"})
    with pytest.raises(DuplicateStudentError) as exc_info:
        aws.create_student({"name": "Anya Patel", "phone": "9000000001", "student_id": "1234567890"})
    assert "College ID Card Number already exists" in str(exc_info.value)


def test_order_history_and_payment_update_use_student_phone_index(service, aws):
    order, _ = service.place_order({
        "customer": {"student_name": "Ravi Kumar", "student_phone": "9123456780", "student_id": ""},
        "items": [{"item_id": "M007", "quantity": 1}],
        "payment_method": "online",
    })
    assert service.list_student_orders("9123456780")[0]["order_id"] == order["order_id"]
    assert aws.mark_order_paid(order["order_id"], "2026-01-01T00:00:00+05:30") is True
    assert service.list_student_orders("9123456780")[0]["payment_status"] == "paid"
