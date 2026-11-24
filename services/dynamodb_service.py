"""DynamoDB storage for APP_MODE=aws.

Table design (see README and docs/architecture.md for the full explanation):
  MenuItems  : partition key item_id. The menu is small, so reading it with Scan is acceptable.
  Orders     : partition key order_id. Staff listing uses the global secondary index
               "ByOrderDate" (partition key order_date, sort key created_at), which is a Query,
               never a full-table Scan.

boto3 finds credentials automatically. On EC2 those come from the instance profile (IAM role).
No access keys are stored in this code.
"""
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from services.errors import DuplicateItemError, DuplicateOrderError, DuplicateStudentError


def _plain(value):
    """DynamoDB returns numbers as Decimal. Convert them so jsonify can handle them."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _is_condition_failure(exc):
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def _normalize_order(order):
    legacy = {"Pending": "Placed", "Ready": "Ready for Pickup", "Collected": "Completed"}
    if order and order.get("status") in legacy:
        order["status"] = legacy[order["status"]]
    if order:
        order["user_id"] = order.get("user_id") or order.get("student_phone")
        order.setdefault("payment_method", "counter")
        order.setdefault("payment_status", "pay_at_pickup")
    return order


class DynamoStore:
    def __init__(
        self, region, menu_table_name, orders_table_name, date_index_name,
        students_table_name="QuickBite-Students", user_index_name="ByStudentPhone",
    ):
        resource = boto3.resource("dynamodb", region_name=region)
        self.menu = resource.Table(menu_table_name)
        self.orders = resource.Table(orders_table_name)
        self.students = resource.Table(students_table_name)
        self.date_index = date_index_name
        self.user_index = user_index_name

    def list_menu(self):
        items, kwargs = [], {}
        while True:
            response = self.menu.scan(ConsistentRead=True, **kwargs)  # small table, so Scan is acceptable here
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return [_plain(item) for item in sorted(items, key=lambda i: i["item_id"])]

    def upsert_menu_items(self, items):
        with self.menu.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

    def add_menu_item(self, item):
        try:
            self.menu.put_item(Item=item, ConditionExpression="attribute_not_exists(item_id)")
        except ClientError as exc:
            if _is_condition_failure(exc):
                raise DuplicateItemError(item["item_id"]) from exc
            raise

    def update_menu_item(self, item_id, updates):
        if not updates:
            response = self.menu.get_item(Key={"item_id": item_id})
            item = response.get("Item")
            return _plain(item) if item else None
        names = {f"#field{index}": key for index, key in enumerate(updates)}
        values = {f":value{index}": value for index, value in enumerate(updates.values())}
        assignments = [
            f"{name} = :value{index}"
            for index, name in enumerate(names)
        ]
        try:
            response = self.menu.update_item(
                Key={"item_id": item_id},
                UpdateExpression="SET " + ", ".join(assignments),
                ConditionExpression="attribute_exists(item_id)",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if _is_condition_failure(exc):
                return None
            raise
        return _plain(response["Attributes"])

    def get_student_by_phone(self, phone):
        response = self.students.get_item(
            Key={"lookup_key": "phone:" + phone},
            ConsistentRead=True,
        )
        student = response.get("Item")
        if not student or student.get("record_type") != "student":
            return None
        return _plain({
            "phone": student["phone"],
            "student_id": student["student_id"],
            "name": student["name"],
        })

    def create_student(self, student):
        account = {
            "lookup_key": "phone:" + student["phone"],
            "record_type": "student",
            **student,
        }
        id_lock = {
            "lookup_key": "student_id:" + student["student_id"],
            "record_type": "student_id",
            "phone": student["phone"],
        }

        try:
            self.students.meta.client.transact_write_items(
                TransactItems=[
                    {"Put": {
                        "TableName": self.students.name,
                        "Item": account,
                        "ConditionExpression": "attribute_not_exists(lookup_key)",
                    }},
                    {"Put": {
                        "TableName": self.students.name,
                        "Item": id_lock,
                        "ConditionExpression": "attribute_not_exists(lookup_key)",
                    }},
                ]
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
                if self.get_student_by_phone(student["phone"]):
                    raise DuplicateStudentError(
                        "phone", "An account with this phone number already exists."
                    ) from exc
                id_response = self.students.get_item(
                    Key={"lookup_key": "student_id:" + student["student_id"]},
                    ConsistentRead=True,
                )
                if id_response.get("Item"):
                    raise DuplicateStudentError(
                        "student_id", "An account with this College ID Card Number already exists."
                    ) from exc
            raise

    def put_order(self, order):
        try:
            self.orders.put_item(Item=order, ConditionExpression="attribute_not_exists(order_id)")
        except ClientError as exc:
            if _is_condition_failure(exc):
                raise DuplicateOrderError(order["order_id"]) from exc
            raise

    def get_order(self, order_id):
        response = self.orders.get_item(Key={"order_id": order_id})
        item = response.get("Item")
        return _normalize_order(_plain(item)) if item else None

    def list_orders_by_date(self, order_date):
        items, kwargs = [], {
            "IndexName": self.date_index,
            "KeyConditionExpression": Key("order_date").eq(order_date),
            "ScanIndexForward": True,
        }
        while True:
            response = self.orders.query(**kwargs)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return [_normalize_order(_plain(item)) for item in items]

    def list_orders_by_user(self, user_id):
        items, kwargs = [], {
            "IndexName": self.user_index,
            "KeyConditionExpression": Key("student_phone").eq(user_id),
            "ScanIndexForward": False,
        }
        while True:
            response = self.orders.query(**kwargs)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return [_normalize_order(_plain(item)) for item in items]

    def mark_order_paid(self, order_id, updated_at):
        try:
            self.orders.update_item(
                Key={"order_id": order_id},
                UpdateExpression="SET payment_status = :paid, updated_at = :ts",
                ConditionExpression=(
                    "attribute_exists(order_id) AND "
                    "(attribute_not_exists(payment_status) OR payment_status = :pickup)"
                ),
                ExpressionAttributeValues={
                    ":paid": "paid",
                    ":pickup": "pay_at_pickup",
                    ":ts": updated_at,
                },
            )
            return True
        except ClientError as exc:
            if _is_condition_failure(exc):
                return False
            raise

    def update_status(self, order_id, expected_status, new_status, updated_at):
        """Conditional update: only succeeds if the order still has expected_status."""
        legacy = {"Placed": "Pending", "Ready for Pickup": "Ready", "Completed": "Collected"}
        old_status = legacy.get(expected_status)
        condition = "attribute_exists(order_id) AND #s = :expected"
        values = {
            ":new": new_status,
            ":expected": expected_status,
            ":ts": updated_at,
        }
        if old_status:
            condition = "attribute_exists(order_id) AND (#s = :expected OR #s = :legacy)"
            values[":legacy"] = old_status
        try:
            self.orders.update_item(
                Key={"order_id": order_id},
                UpdateExpression="SET #s = :new, updated_at = :ts",
                ConditionExpression=condition,
                ExpressionAttributeNames={"#s": "status"},  # "status" is a DynamoDB reserved word
                ExpressionAttributeValues=values,
            )
            return True
        except ClientError as exc:
            if _is_condition_failure(exc):
                return False
            raise
