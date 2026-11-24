"""Application tests in demo mode. No AWS calls are made: SMS is replaced by a mock."""
import re
from unittest.mock import MagicMock

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from services.demo_store import DemoStore

STAFF_PASSWORD = "correct-horse-battery"


@pytest.fixture
def notifier():
    mock = MagicMock()
    mock.send.return_value = "accepted"
    return mock


@pytest.fixture
def client(tmp_path, notifier):
    store = DemoStore(str(tmp_path / "test.db"))
    store.seed_if_empty()
    app = create_app(
        store=store,
        notifier=notifier,
        settings={
            "APP_MODE": "demo",
            "SECRET_KEY": "test-secret-key",
            "STAFF_PASSWORD_HASH": generate_password_hash(STAFF_PASSWORD),
            "TESTING": True,
        },
    )
    return app.test_client()


def place(client, items, name="Priya Sharma", phone="9876543210", student_id=None, payment_method="counter"):
    student_id = student_id or phone
    registration = client.post("/api/student/register", json={
        "name": name, "phone": phone, "student_id": student_id,
    })
    if registration.status_code == 409:
        login = client.post("/api/student/login", json={"name": name, "phone": phone})
        assert login.status_code == 200
    else:
        assert registration.status_code == 201
    body = {
        "customer": {"student_name": name, "student_phone": phone, "student_id": student_id},
        "items": items,
        "payment_method": payment_method,
    }
    return client.post("/api/orders", json=body)


def staff_login(client):
    response = client.post("/staff/login", data={"password": STAFF_PASSWORD})
    assert response.status_code == 302


# ---------- Menu and pages ----------

def test_menu_lists_twelve_items_and_categories(client):
    data = client.get("/api/menu").get_json()
    assert len(data["items"]) == 12
    assert set(data["categories"]) == {"Breakfast", "Snacks", "Meals", "Beverages"}


def test_menu_category_and_search_filters(client):
    beverages = client.get("/api/menu?category=Beverages").get_json()["items"]
    assert beverages and all(i["category"] == "Beverages" for i in beverages)
    dosa = client.get("/api/menu?q=dosa").get_json()["items"]
    assert [i["name"] for i in dosa] == ["Masala Dosa"]


def test_pages_render(client):
    for path in ["/", "/track", "/staff/login"]:
        assert client.get(path).status_code == 200, path
    assert b"QuickBite Login" in client.get("/").data
    for path in ["/cart", "/checkout"]:
        assert client.get(path).status_code == 302
    assert client.get("/account").status_code == 302


def test_skip_mode_browses_menu_but_ordering_routes_back_to_login(client):
    response = client.get("/?browse=1")
    assert response.status_code == 200
    assert b'data-browse-only="true"' in response.data
    assert b"Sign In" in response.data
    cart = client.get("/cart")
    assert cart.status_code == 302
    assert "message=login-required" in cart.headers["Location"]
    login = client.get(cart.headers["Location"])
    assert b"Please log in to place an order." in login.data


def test_demo_banner_is_shown(client):
    assert b"DEMO MODE" in client.get("/").data


def test_student_registration_validation_duplicate_checks_and_persistent_login(client):
    account = {"name": "Priya Sharma", "phone": "9876543210", "student_id": "1234567890"}
    assert client.post("/api/student/register", json={**account, "phone": "12345"}).status_code == 400
    assert client.post("/api/student/register", json={**account, "student_id": "1234"}).status_code == 400

    created = client.post("/api/student/register", json=account)
    assert created.status_code == 201
    assert b"Skip the queue" in client.get("/").data

    duplicate_phone = client.post(
        "/api/student/register",
        json={"name": "Another Student", "phone": account["phone"], "student_id": "9876543210"},
    )
    assert duplicate_phone.status_code == 409
    assert duplicate_phone.get_json()["field"] == "phone"
    duplicate_id = client.post(
        "/api/student/register",
        json={"name": "Another Student", "phone": "9000012345", "student_id": account["student_id"]},
    )
    assert duplicate_id.status_code == 409
    assert duplicate_id.get_json()["field"] == "student_id"


def test_student_login_requires_matching_name_and_phone(client):
    place(client, [{"item_id": "M001", "quantity": 1}])
    client.post("/api/student/logout")
    response = client.post("/api/student/login", json={"name": "Wrong Name", "phone": "9876543210"})
    assert response.status_code == 401
    assert response.get_json()["error"] == "No account found. Please create an account."
    assert client.post("/api/student/login", json={"name": "Priya Sharma", "phone": "9876543210"}).status_code == 200
    assert b"Skip the queue" in client.get("/").data


def test_order_api_requires_student_login(client):
    response = client.post("/api/orders", json={"items": [{"item_id": "M001", "quantity": 1}]})
    assert response.status_code == 401


# ---------- Ordering ----------

def test_order_is_priced_on_the_server(client):
    # The client tries to set its own price (1 rupee). The server must ignore it.
    items = [{"item_id": "M001", "quantity": 2, "price": 1}, {"item_id": "M011", "quantity": 1}]
    response = place(client, items)
    assert response.status_code == 201
    body = response.get_json()
    assert body["total_amount"] == 60 * 2 + 15
    assert re.fullmatch(r"QB-\d{4}-[0-9A-F]{8}", body["order_id"])


def test_order_is_tracked_without_exposing_phone(client):
    order_id = place(client, [{"item_id": "M003", "quantity": 1}]).get_json()["order_id"]
    tracked = client.get(f"/api/orders/{order_id}")
    assert tracked.status_code == 200
    data = tracked.get_json()
    assert data["status"] == "Placed"
    assert "student_phone" not in data
    assert data["estimated_prep_minutes"] >= 5
    assert data["payment_method"] == "counter"
    assert data["payment_status"] == "pay_at_pickup"


def test_unknown_order_returns_404(client):
    assert client.get("/api/orders/QB-2026-00000000").status_code == 404
    assert client.get("/api/orders/not-an-id").status_code == 404


def test_confirmation_page_shows_order(client):
    order_id = place(client, [{"item_id": "M011", "quantity": 2}]).get_json()["order_id"]
    page = client.get(f"/confirmation/{order_id}")
    assert page.status_code == 200
    assert b"placed successfully" in page.data


@pytest.mark.parametrize("items", [
    [],
    [{"item_id": "M001", "quantity": 0}],
    [{"item_id": "M001", "quantity": 11}],
    [{"item_id": "M001", "quantity": "two"}],
    [{"item_id": "M999", "quantity": 1}],
    [{"item_id": "M009", "quantity": 1}],          # Vada Pav is unavailable
    [{"item_id": "M001", "quantity": 6}, {"item_id": "M001", "quantity": 6}],  # merged total over limit
])
def test_invalid_cart_is_rejected(client, items):
    response = place(client, items)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_invalid_customer_details_are_rejected(client):
    assert client.post("/api/student/register", json={
        "name": "A", "phone": "9876543210", "student_id": "1234567890",
    }).status_code == 400
    assert client.post("/api/student/register", json={
        "name": "Priya Sharma", "phone": "12345", "student_id": "1234567890",
    }).status_code == 400
    assert client.post("/api/student/register", json={
        "name": "Priya Sharma", "phone": "9876543210", "student_id": "bad",
    }).status_code == 400


def test_order_is_placed_even_if_sms_fails(client, notifier):
    notifier.send.return_value = "failed"
    response = place(client, [{"item_id": "M001", "quantity": 1}])
    assert response.status_code == 201
    assert response.get_json()["notification"] == "failed"


# ---------- Staff authentication ----------

def test_staff_api_requires_login(client):
    assert client.get("/api/staff/orders").status_code == 401
    assert client.get("/api/staff/menu").status_code == 401
    assert client.patch("/api/staff/orders/QB-2026-00000000/status", json={"status": "Preparing"}).status_code == 401
    assert client.patch("/api/staff/orders/QB-2026-00000000/payment", json={"payment_status": "paid"}).status_code == 401


def test_staff_dashboard_redirects_when_logged_out(client):
    response = client.get("/staff")
    assert response.status_code == 302
    assert "/staff/login" in response.headers["Location"]


def test_wrong_password_is_rejected(client):
    response = client.post("/staff/login", data={"password": "wrong"})
    assert response.status_code == 200
    assert b"Incorrect password" in response.data
    assert client.get("/api/staff/orders").status_code == 401


def test_login_and_logout(client):
    staff_login(client)
    assert client.get("/api/staff/orders").status_code == 200
    client.get("/staff/logout")
    assert client.get("/api/staff/orders").status_code == 401


def test_staff_password_hash_is_not_plain_text(client):
    # The app must hold only a hash of the password, never the password itself.
    app_config = client.application.config
    assert STAFF_PASSWORD not in app_config["STAFF_PASSWORD_HASH"]


# ---------- Staff order management ----------

def test_staff_list_counts_and_search(client):
    place(client, [{"item_id": "M001", "quantity": 1}], name="Arjun Rao", phone="9000011111")
    place(client, [{"item_id": "M011", "quantity": 1}], name="Meera Nair", phone="9000022222")
    staff_login(client)

    data = client.get("/api/staff/orders").get_json()
    assert data["counts"]["Total"] == 2
    assert data["counts"]["Placed"] == 2

    by_name = client.get("/api/staff/orders?q=arjun").get_json()["orders"]
    assert [o["student_name"] for o in by_name] == ["Arjun Rao"]
    by_phone = client.get("/api/staff/orders?q=9000022222").get_json()["orders"]
    assert [o["student_name"] for o in by_phone] == ["Meera Nair"]
    by_id = client.get(f"/api/staff/orders?q={by_name[0]['order_id']}").get_json()["orders"]
    assert len(by_id) == 1


def test_status_moves_forward_only_and_sms_fires_on_ready(client, notifier):
    order_id = place(client, [{"item_id": "M003", "quantity": 1}]).get_json()["order_id"]
    staff_login(client)
    url = f"/api/staff/orders/{order_id}/status"

    # Skipping a step is refused
    assert client.patch(url, json={"status": "Ready for Pickup"}).status_code == 400

    assert client.patch(url, json={"status": "Preparing"}).get_json()["status"] == "Preparing"
    assert notifier.send.call_count == 1  # order placed SMS only, no Ready SMS yet

    ready = client.patch(url, json={"status": "Ready for Pickup"})
    assert ready.status_code == 200
    assert ready.get_json()["notification"] == "accepted"
    assert notifier.send.call_count == 2
    ready_message = notifier.send.call_args_list[-1][0][1]
    assert "is ready for pickup" in ready_message
    assert order_id in ready_message

    assert client.patch(url, json={"status": "Completed"}).status_code == 200
    assert notifier.send.call_count == 2  # no extra SMS on Completed

    # Completed is final
    assert client.patch(url, json={"status": "Placed"}).status_code == 400
    assert client.get(f"/api/orders/{order_id}").status_code == 404
    completed = client.get("/api/staff/orders?status=Completed").get_json()
    assert [order["order_id"] for order in completed["orders"]] == [order_id]


def test_ready_update_succeeds_even_if_sms_fails(client, notifier):
    order_id = place(client, [{"item_id": "M011", "quantity": 1}]).get_json()["order_id"]
    staff_login(client)
    url = f"/api/staff/orders/{order_id}/status"
    client.patch(url, json={"status": "Preparing"})
    notifier.send.return_value = "failed"
    response = client.patch(url, json={"status": "Ready for Pickup"})
    assert response.status_code == 200
    assert response.get_json()["status"] == "Ready for Pickup"


def test_unknown_order_status_update_returns_404(client):
    staff_login(client)
    response = client.patch("/api/staff/orders/QB-2026-00000000/status", json={"status": "Preparing"})
    assert response.status_code == 404


def test_tracking_reflects_status_changes(client):
    order_id = place(client, [{"item_id": "M011", "quantity": 1}]).get_json()["order_id"]
    staff_login(client)
    client.patch(f"/api/staff/orders/{order_id}/status", json={"status": "Preparing"})
    tracked = client.get(f"/api/orders/{order_id}").get_json()
    assert tracked["status"] == "Preparing"
    assert tracked["status_index"] == 1


def test_payment_method_history_and_staff_paid_action(client):
    order_id = place(
        client, [{"item_id": "M011", "quantity": 1}], payment_method="online",
    ).get_json()["order_id"]
    assert client.get("/account").status_code == 200
    history = client.get("/api/student/orders").get_json()["orders"]
    assert history[0]["order_id"] == order_id
    assert history[0]["payment_method"] == "online"
    assert history[0]["payment_status"] == "pay_at_pickup"

    staff_login(client)
    paid = client.patch(f"/api/staff/orders/{order_id}/payment", json={"payment_status": "paid"})
    assert paid.status_code == 200
    assert paid.get_json()["payment_status"] == "paid"
    assert client.post("/api/student/login", json={"name": "Priya Sharma", "phone": "9876543210"}).status_code == 200
    assert client.get("/api/student/orders").get_json()["orders"][0]["payment_status"] == "paid"


def test_completed_order_remains_in_account_history_but_public_tracking_hides_it(client):
    order_id = place(client, [{"item_id": "M011", "quantity": 1}]).get_json()["order_id"]
    staff_login(client)
    status_url = f"/api/staff/orders/{order_id}/status"
    for status in ("Preparing", "Ready for Pickup", "Completed"):
        assert client.patch(status_url, json={"status": status}).status_code == 200
    assert client.get(f"/api/orders/{order_id}").status_code == 404

    assert client.post("/api/student/login", json={"name": "Priya Sharma", "phone": "9876543210"}).status_code == 200
    tracked = client.get(f"/api/orders/{order_id}").get_json()
    assert tracked["status"] == "Completed"
    history = client.get("/api/student/orders").get_json()["orders"]
    assert history[0]["status"] == "Completed"


def test_staff_can_manage_menu_and_unavailable_items_cannot_be_ordered(client):
    staff_login(client)
    item_id = "M001"
    updated = client.patch(f"/api/staff/menu/{item_id}", json={
        "name": "Updated Sandwich", "price": 65, "available": False,
    })
    assert updated.status_code == 200
    menu_item = next(item for item in client.get("/api/menu").get_json()["items"] if item["item_id"] == item_id)
    assert (menu_item["name"], menu_item["price"], menu_item["available"]) == ("Updated Sandwich", 65, False)

    unavailable = place(client, [{"item_id": item_id, "quantity": 1}])
    assert unavailable.status_code == 400
    staff_login(client)

    added = client.post("/api/staff/menu", json={
        "name": "New Tea", "price": 22, "category": "Beverages",
        "image_url": "", "available": True,
    })
    assert added.status_code == 201
    added_item = added.get_json()["item"]
    assert added_item["name"] == "New Tea"
    assert added_item in client.get("/api/menu").get_json()["items"]
    new_order = place(client, [{"item_id": added_item["item_id"], "quantity": 1}])
    assert new_order.status_code == 201
    assert new_order.get_json()["total_amount"] == 22
