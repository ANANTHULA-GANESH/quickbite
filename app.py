"""QuickBite: campus canteen pre-order web application (Flask).

Local development (demo mode):  python app.py          -> http://127.0.0.1:5000
Production on EC2:              gunicorn app:app       (see deployment/quickbite.service)
"""
import logging
import secrets
from datetime import timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from config import Config
from services.errors import ConflictError, NotFoundError, ValidationError
from services.menu_data import CATEGORIES
from services.menu_service import MenuService
from services.order_service import OrderService, estimate_prep_minutes
from services.sns_service import SmsNotifier
from services.student_service import StudentService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def build_store(settings):
    """Choose the storage backend for the configured mode."""
    if settings["APP_MODE"] == "aws":
        from services.dynamodb_service import DynamoStore

        return DynamoStore(
            settings["AWS_REGION"],
            settings["MENU_TABLE_NAME"],
            settings["ORDERS_TABLE_NAME"],
            settings["ORDERS_DATE_INDEX"],
            settings["STUDENTS_TABLE_NAME"],
            settings["ORDERS_USER_INDEX"],
        )
    from services.demo_store import DemoStore

    store = DemoStore(settings["DEMO_DB_PATH"])
    store.seed_if_empty()
    return store


def create_app(store=None, notifier=None, settings=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if settings:
        app.config.update(settings)

    mode = app.config["APP_MODE"]
    if mode not in ("demo", "aws"):
        raise RuntimeError("APP_MODE must be 'demo' or 'aws'.")
    if not app.config["SECRET_KEY"]:
        if mode == "aws":
            raise RuntimeError("SECRET_KEY must be set when APP_MODE=aws.")
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning("SECRET_KEY not set. Using a temporary key; staff sessions reset on restart.")

    app.permanent_session_lifetime = timedelta(hours=app.config["STAFF_SESSION_HOURS"])

    store = store or build_store(app.config)
    notifier = notifier or SmsNotifier(
        enabled=app.config["SNS_ENABLED"],
        region=app.config["AWS_REGION"],
        sender_id=app.config["SNS_SMS_SENDER_ID"],
    )
    orders = OrderService(
        store, notifier, ZoneInfo(app.config["TIMEZONE"]),
        app.config["MAX_CART_LINES"], app.config["MAX_QUANTITY"],
    )
    menu = MenuService(store)
    students = StudentService(store)

    # ---------- Shared template data, security headers and JSON error handling ----------

    @app.context_processor
    def inject_globals():
        student = store.get_student_by_phone(session["student_phone"]) if session.get("student_phone") else None
        return {
            "app_mode": mode,
            "categories": CATEGORIES,
            "student": student,
            "browse_only": bool(not student and request.args.get("browse") == "1"),
        }

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.path.startswith(("/staff", "/api/staff", "/api/student")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(ValidationError)
    def handle_validation(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(NotFoundError)
    def handle_not_found(exc):
        return jsonify(error=str(exc)), 404

    @app.errorhandler(ConflictError)
    def handle_conflict(exc):
        response = {"error": str(exc)}
        if getattr(exc, "field", None):
            response["field"] = exc.field
        return jsonify(response), 409

    # ---------- Staff authentication ----------

    def is_staff():
        return bool(session.get("staff"))

    def staff_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not is_staff():
                if request.path.startswith("/api/"):
                    return jsonify(error="Staff login required."), 401
                return redirect(url_for("staff_login"))
            return view(*args, **kwargs)

        return wrapper

    def student_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not session.get("student_phone") or not store.get_student_by_phone(session["student_phone"]):
                if request.path.startswith("/api/"):
                    return jsonify(error="Student login required."), 401
                if request.path in ("/cart", "/checkout"):
                    return redirect(url_for("index", message="login-required"))
                return redirect(url_for("index"))
            return view(*args, **kwargs)

        return wrapper

    @app.route("/staff/login", methods=["GET", "POST"])
    def staff_login():
        error = None
        configured = bool(app.config["STAFF_PASSWORD_HASH"])
        if request.method == "POST":
            if not configured:
                error = "Staff login is not configured yet. Set STAFF_PASSWORD_HASH on the server."
            elif check_password_hash(app.config["STAFF_PASSWORD_HASH"], request.form.get("password", "")):
                session.clear()
                session["staff"] = True
                session.permanent = True
                return redirect(url_for("staff_dashboard"))
            else:
                error = "Incorrect password. Please try again."
        return render_template("staff_login.html", error=error, configured=configured)

    @app.get("/staff/logout")
    def staff_logout():
        session.clear()
        return redirect(url_for("index"))

    # ---------- Student pages ----------

    @app.get("/")
    def index():
        student = store.get_student_by_phone(session["student_phone"]) if session.get("student_phone") else None
        if student:
            return render_template("index.html", browse_only=False)
        if request.args.get("browse") == "1":
            return render_template("index.html", browse_only=True)
        login_message = (
            "Please log in to place an order."
            if request.args.get("message") == "login-required" else None
        )
        return render_template("student_login.html", login_message=login_message)

    @app.get("/cart")
    @student_required
    def cart_page():
        return render_template("cart.html")

    @app.get("/checkout")
    @student_required
    def checkout_page():
        return render_template("checkout.html", student=store.get_student_by_phone(session["student_phone"]))

    @app.get("/account")
    @student_required
    def student_account():
        return render_template("student_account.html", student=store.get_student_by_phone(session["student_phone"]))

    @app.get("/confirmation/<order_id>")
    def confirmation_page(order_id):
        order = orders.get_public_order(order_id.upper())
        if order is None:
            abort(404)
        return render_template("confirmation.html", order=order)

    @app.get("/track")
    def track_lookup():
        order_id = request.args.get("order_id", "").strip().upper()
        if order_id:
            return redirect(url_for("track_order", order_id=order_id))
        return render_template("tracking.html", order_id="")

    @app.get("/track/<order_id>")
    def track_order(order_id):
        return render_template("tracking.html", order_id=order_id.upper())

    # ---------- Staff pages ----------

    @app.get("/staff")
    @staff_required
    def staff_dashboard():
        return render_template("staff_dashboard.html")

    # ---------- JSON API: student side ----------

    @app.get("/api/menu")
    def api_menu():
        category = request.args.get("category", "all")
        query = request.args.get("q", "").strip().lower()
        all_items = store.list_menu()
        items = all_items
        if category != "all":
            items = [i for i in items if i["category"] == category]
        if query:
            items = [i for i in items if query in (i["name"] + " " + i["description"]).lower()]
        categories = list(dict.fromkeys(item["category"] for item in all_items))
        return jsonify(items=items, categories=categories)

    @app.post("/api/student/register")
    def api_student_register():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValidationError("Send your account details as JSON.")
        student = students.register(payload)
        session.clear()
        session["student_phone"] = student["phone"]
        session.permanent = True
        return jsonify(ok=True), 201

    @app.post("/api/student/login")
    def api_student_login():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValidationError("Send your login details as JSON.")
        student = students.authenticate(payload)
        if student is None:
            return jsonify(error="No account found. Please create an account."), 401
        session.clear()
        session["student_phone"] = student["phone"]
        session.permanent = True
        return jsonify(ok=True)

    @app.post("/api/student/logout")
    @student_required
    def api_student_logout():
        session.clear()
        return jsonify(ok=True)

    @app.post("/student/logout")
    @student_required
    def student_logout():
        session.clear()
        return redirect(url_for("index"))

    @app.post("/api/orders")
    @student_required
    def api_place_order():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValidationError("Send your order as JSON.")
        student = store.get_student_by_phone(session["student_phone"])
        payload["customer"] = {
            "student_name": student["name"],
            "student_phone": student["phone"],
            "student_id": student["student_id"],
        }
        payload["user_id"] = student["phone"]
        order, notification = orders.place_order(payload)
        return jsonify(
            order_id=order["order_id"],
            status=order["status"],
            total_amount=order["total_amount"],
            estimated_prep_minutes=estimate_prep_minutes(order["items"]),
            notification=notification,
        ), 201

    @app.get("/api/orders/<order_id>")
    def api_track_order(order_id):
        student_phone = session.get("student_phone")
        order = (
            orders.get_student_order(order_id.upper(), student_phone)
            if student_phone else orders.get_public_order(order_id.upper())
        )
        if order is None:
            return jsonify(error="Order not found. Check the order ID and try again."), 404
        return jsonify(order)

    @app.get("/api/student/orders")
    @student_required
    def api_student_orders():
        return jsonify(orders=orders.list_student_orders(session["student_phone"]))

    # ---------- JSON API: staff side (login required) ----------

    @app.get("/api/staff/orders")
    @staff_required
    def api_staff_orders():
        result = orders.list_staff_orders(
            order_date=request.args.get("date") or None,
            status=request.args.get("status") or None,
            query=request.args.get("q") or None,
        )
        return jsonify(result)

    @app.patch("/api/staff/orders/<order_id>/status")
    @staff_required
    def api_update_status(order_id):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValidationError("Send the new status as JSON.")
        order, notification = orders.update_status(order_id.upper(), payload.get("status"))
        return jsonify(order_id=order["order_id"], status=order["status"], notification=notification)

    @app.patch("/api/staff/orders/<order_id>/payment")
    @staff_required
    def api_mark_order_paid(order_id):
        order = orders.mark_order_paid(order_id.upper())
        return jsonify(order_id=order["order_id"], payment_status=order["payment_status"])

    @app.get("/api/staff/menu")
    @staff_required
    def api_staff_menu():
        return jsonify(items=store.list_menu())

    @app.post("/api/staff/menu")
    @staff_required
    def api_add_menu_item():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValidationError("Send the menu item as JSON.")
        return jsonify(item=menu.add_item(payload)), 201

    @app.patch("/api/staff/menu/<item_id>")
    @staff_required
    def api_update_menu_item(item_id):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValidationError("Send item changes as JSON.")
        return jsonify(item=menu.update_item(item_id, payload))

    @app.get("/healthz")
    def health():
        """Cheap health check for the load balancer or uptime monitor. Does not touch the database."""
        return "ok", 200

    return app


# Module-level app so gunicorn can run `app:app`.
app = create_app()

if __name__ == "__main__":
    # Development server only. In production, run gunicorn behind nginx.
    app.run(host="127.0.0.1", port=5000, debug=False)
