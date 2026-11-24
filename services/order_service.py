"""Business rules for orders.

The browser sends only item IDs and quantities. Prices, totals and order IDs are decided
here on the server, using the menu stored in the database.
"""
import re
import secrets
from datetime import datetime

from services.errors import ConflictError, DuplicateOrderError, NotFoundError, ValidationError

ORDER_STATUSES = ("Placed", "Preparing", "Ready for Pickup", "Completed")
# Staff may only move an order one step forward. Students cannot change status at all.
NEXT_STATUS = {"Placed": "Preparing", "Preparing": "Ready for Pickup", "Ready for Pickup": "Completed"}

NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z .'-]{1,59}")
STUDENT_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{0,20}")
ORDER_ID_PATTERN = re.compile(r"QB-\d{4}-[0-9A-F]{8}")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
E164_PATTERN = re.compile(r"\+[1-9]\d{7,14}")
DEFAULT_COUNTRY_CODE = "+91"  # Indian mobile numbers. Change this for another country.


def valid_order_id(order_id):
    return bool(ORDER_ID_PATTERN.fullmatch(order_id or ""))


def normalize_phone(raw):
    """Return the phone number in E.164 format (for example +919876543210)."""
    digits = re.sub(r"[\s()-]", "", raw or "")
    if re.fullmatch(r"\d{10}", digits):
        digits = DEFAULT_COUNTRY_CODE + digits
    elif re.fullmatch(r"91\d{10}", digits):
        digits = "+" + digits
    if not E164_PATTERN.fullmatch(digits):
        raise ValidationError("Enter a valid 10-digit mobile number, for example 9876543210.")
    return digits


def validate_customer(data):
    name = (data.get("student_name") or "").strip()
    if not NAME_PATTERN.fullmatch(name):
        raise ValidationError("Enter your name (2 to 60 letters, spaces, dots or apostrophes).")
    student_id = (data.get("student_id") or "").strip()
    if not STUDENT_ID_PATTERN.fullmatch(student_id):
        raise ValidationError("Student ID can contain only letters, digits and hyphens (max 20).")
    return {
        "student_name": name,
        "student_phone": normalize_phone(data.get("student_phone")),
        "student_id": student_id,
    }


def build_cart_lines(raw_items, menu_by_id, max_lines, max_qty):
    """Check the cart against the menu and price every line from the database."""
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationError("Your cart is empty.")
    if len(raw_items) > max_lines:
        raise ValidationError(f"An order can contain at most {max_lines} different items.")

    quantities = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValidationError("Invalid cart data.")
        item_id = str(raw.get("item_id", "")).strip()
        try:
            quantity = int(raw.get("quantity"))
        except (TypeError, ValueError):
            raise ValidationError("Quantity must be a whole number.")
        if quantity < 1:
            raise ValidationError("Quantity must be at least 1.")
        item = menu_by_id.get(item_id)
        if item is None:
            raise ValidationError("One of the items in your cart is not on the menu.")
        if not item["available"]:
            raise ValidationError(f"{item['name']} is currently unavailable. Please remove it from your cart.")
        quantities[item_id] = quantities.get(item_id, 0) + quantity

    lines = []
    for item_id, quantity in quantities.items():
        if quantity > max_qty:
            raise ValidationError(f"You can order at most {max_qty} of each item.")
        item = menu_by_id[item_id]
        lines.append({
            "item_id": item_id,
            "name": item["name"],
            "unit_price": item["price"],
            "quantity": quantity,
            "line_total": item["price"] * quantity,
        })
    return lines


def new_order_id(now):
    """Order IDs look like QB-2026-3F9A1C2B. The random part makes IDs hard to guess."""
    return f"QB-{now.year}-{secrets.token_hex(4).upper()}"


def build_order(customer, lines, now, payment_method, user_id):
    stamp = now.isoformat(timespec="seconds")
    return {
        "order_id": new_order_id(now),
        "user_id": user_id,
        **customer,
        "items": lines,
        "total_amount": sum(line["line_total"] for line in lines),
        "status": "Placed",
        "payment_method": payment_method,
        "payment_status": "pay_at_pickup",
        "order_date": now.strftime("%Y-%m-%d"),
        "created_at": stamp,
        "updated_at": stamp,
    }


def estimate_prep_minutes(items):
    """Rough estimate for display only: 5 minutes plus 2 per portion, capped at 25."""
    portions = sum(item["quantity"] for item in items)
    return min(5 + 2 * portions, 25)


def public_order_view(order):
    """What anyone holding the order ID may see. The phone number is never included."""
    fields = (
        "order_id", "student_name", "items", "total_amount", "status",
        "order_date", "created_at", "updated_at", "payment_method", "payment_status",
    )
    view = {key: order.get(key) for key in fields}
    view["estimated_prep_minutes"] = estimate_prep_minutes(order["items"])
    view["status_index"] = ORDER_STATUSES.index(order["status"])
    return view


def order_placed_message(order):
    return (f"QuickBite: Your order {order['order_id']} has been placed successfully. "
            f"Total: ₹{order['total_amount']}.")


def order_ready_message(order):
    return (f"QuickBite: Your order {order['order_id']} is ready for pickup. "
            "Please collect it from the campus canteen.")


class OrderService:
    """Coordinates validation, storage and notifications. It knows nothing about HTTP."""

    def __init__(self, store, notifier, tz, max_lines, max_qty):
        self.store = store
        self.notifier = notifier
        self.tz = tz
        self.max_lines = max_lines
        self.max_qty = max_qty

    def now(self):
        return datetime.now(self.tz)

    def place_order(self, payload):
        customer = validate_customer(payload.get("customer") or {})
        payment_method = payload.get("payment_method", "counter")
        if payment_method not in ("counter", "online"):
            raise ValidationError("Choose Pay at Counter or Pay Online.")
        menu_by_id = {item["item_id"]: item for item in self.store.list_menu()}
        lines = build_cart_lines(payload.get("items"), menu_by_id, self.max_lines, self.max_qty)

        now = self.now()
        order = build_order(customer, lines, now, payment_method, customer["student_phone"])
        self._save_with_unique_id(order, now)

        # A failed SMS must never fail the order. The notifier returns a status instead of raising.
        notification = self.notifier.send(order["student_phone"], order_placed_message(order), order["order_id"])
        return order, notification

    def _save_with_unique_id(self, order, now):
        for _ in range(3):
            try:
                self.store.put_order(order)
                return
            except DuplicateOrderError:
                order["order_id"] = new_order_id(now)
        raise ConflictError("Could not create a unique order number. Please try again.")

    def get_public_order(self, order_id):
        if not valid_order_id(order_id):
            return None
        order = self.store.get_order(order_id)
        return public_order_view(order) if order and order["status"] != "Completed" else None

    def get_student_order(self, order_id, user_id):
        if not valid_order_id(order_id):
            return None
        order = self.store.get_order(order_id)
        normalized_user_id = normalize_phone(user_id)
        if order is None or order.get("user_id", order.get("student_phone")) != normalized_user_id:
            return None
        return public_order_view(order)

    def list_student_orders(self, phone):
        user_id = normalize_phone(phone)
        orders = self.store.list_orders_by_user(user_id)
        return [public_order_view(order) for order in orders]

    def mark_order_paid(self, order_id):
        if not valid_order_id(order_id):
            raise NotFoundError("Order not found.")
        order = self.store.get_order(order_id)
        if order is None:
            raise NotFoundError("Order not found.")
        if order.get("payment_status") in ("paid", "paid_at_order"):
            return order
        updated_at = self.now().isoformat(timespec="seconds")
        if not self.store.mark_order_paid(order_id, updated_at):
            raise ConflictError("This order's payment was just updated. Refresh and try again.")
        order["payment_status"] = "paid"
        order["updated_at"] = updated_at
        return order

    def list_staff_orders(self, order_date=None, status=None, query=None):
        if order_date and not DATE_PATTERN.fullmatch(order_date):
            raise ValidationError("Date must be in YYYY-MM-DD format.")
        day = order_date or self.now().strftime("%Y-%m-%d")
        all_orders = self.store.list_orders_by_date(day)

        counts = {state: 0 for state in ORDER_STATUSES}
        for order in all_orders:
            counts[order["status"]] = counts.get(order["status"], 0) + 1
        counts["Total"] = len(all_orders)

        visible = all_orders
        if status:
            if status not in ORDER_STATUSES:
                raise ValidationError("Unknown status filter.")
            visible = [o for o in visible if o["status"] == status]
        if query:
            needle = query.strip().lower()
            phone_digits = re.sub(r"\D", "", needle)
            visible = [
                o for o in visible
                if needle in o["order_id"].lower()
                or needle in o["student_name"].lower()
                or (phone_digits and phone_digits in re.sub(r"\D", "", o["student_phone"]))
            ]
        visible.sort(key=lambda o: o["created_at"], reverse=True)
        return {"date": day, "counts": counts, "orders": visible}

    def update_status(self, order_id, new_status):
        if not valid_order_id(order_id):
            raise NotFoundError("Order not found.")
        order = self.store.get_order(order_id)
        if order is None:
            raise NotFoundError("Order not found.")

        current = order["status"]
        if NEXT_STATUS.get(current) != new_status:
            allowed = NEXT_STATUS.get(current)
            raise ValidationError(
                f"This order is {current}. " + (f"It can only move to {allowed}." if allowed else "It cannot change further.")
            )

        updated_at = self.now().isoformat(timespec="seconds")
        # Conditional write: fails if someone else changed the status in the meantime.
        if not self.store.update_status(order_id, current, new_status, updated_at):
            raise ConflictError("This order was just updated by someone else. Refresh and try again.")

        order["status"] = new_status
        order["updated_at"] = updated_at
        notification = "not_required"
        if new_status == "Ready for Pickup":
            notification = self.notifier.send(order["student_phone"], order_ready_message(order), order_id)
        return order, notification
