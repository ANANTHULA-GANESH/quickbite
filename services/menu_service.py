"""Validation and staff operations for the shared menu."""
import secrets
from urllib.parse import urlparse

from services.errors import DuplicateItemError, NotFoundError, ValidationError
from services.menu_data import CATEGORIES


def _validate_price(value):
    if isinstance(value, bool):
        raise ValidationError("Price must be a positive whole number.")
    try:
        price = int(value)
    except (TypeError, ValueError):
        raise ValidationError("Price must be a positive whole number.")
    if price < 1 or str(value).strip() != str(price):
        raise ValidationError("Price must be a positive whole number.")
    return price


def _validate_name(value):
    name = value.strip() if isinstance(value, str) else ""
    if not name or len(name) > 80:
        raise ValidationError("Item name must be between 1 and 80 characters.")
    return name


def _validate_image_url(value):
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or len(value) > 500:
        raise ValidationError("Image URL must be at most 500 characters.")
    parsed = urlparse(value)
    if value.startswith("/static/") or parsed.scheme in ("http", "https") and parsed.netloc:
        return value
    raise ValidationError("Image URL must use http://, https://, or a /static/ path.")


class MenuService:
    def __init__(self, store):
        self.store = store

    def add_item(self, payload):
        name = _validate_name(payload.get("name"))
        price = _validate_price(payload.get("price"))
        category = payload.get("category")
        if category not in CATEGORIES:
            raise ValidationError("Choose a valid menu category.")
        image_url = _validate_image_url(payload.get("image_url"))
        available = payload.get("available", True)
        if not isinstance(available, bool):
            raise ValidationError("Availability must be yes or no.")

        item = {
            "item_id": "",
            "name": name,
            "category": category,
            "price": price,
            "emoji": "🍽️",
            "description": "",
            "image_url": image_url,
            "available": available,
            "featured": False,
        }
        for _ in range(3):
            item["item_id"] = "M" + secrets.token_hex(4).upper()
            try:
                self.store.add_menu_item(item)
                return item
            except DuplicateItemError:
                continue
        raise ValidationError("Could not create a unique menu item. Please try again.")

    def update_item(self, item_id, payload):
        if not isinstance(payload, dict) or not payload:
            raise ValidationError("Send at least one item change.")
        updates = {}
        if "name" in payload:
            updates["name"] = _validate_name(payload["name"])
        if "price" in payload:
            updates["price"] = _validate_price(payload["price"])
        if "available" in payload:
            if not isinstance(payload["available"], bool):
                raise ValidationError("Availability must be yes or no.")
            updates["available"] = payload["available"]
        if set(payload) - {"name", "price", "available"}:
            raise ValidationError("Only name, price and availability can be changed here.")

        item = self.store.update_menu_item(item_id, updates)
        if item is None:
            raise NotFoundError("Menu item not found.")
        return item
