# QuickBite: Campus Canteen Pre-Order App

QuickBite lets students create an account, browse the canteen menu, pre-order food, track preparation, and get an SMS when it is ready for pickup. Canteen staff manage orders through Placed → Preparing → Ready for Pickup → Completed and can manage menu items.

## Features

- **Student side:** account login/registration, browse-only skip mode, live menu availability, cart, checkout with counter/online preference, order tracking, and account order history.
- **Staff side:** password-protected dashboard with live orders, Completed and payment status controls, and Manage Items for availability, prices and new items.
- **Security:** prices and totals are calculated on the server, students cannot change status, staff login uses a salted password hash from an environment variable, and no AWS keys are stored in the code.
- **Notifications:** SMS on order placement and on Ready, sent through Amazon SNS. A failed SMS never fails an order.
- **Two modes:** `APP_MODE=demo` runs fully locally with SQLite. `APP_MODE=aws` uses DynamoDB and SNS.

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, vanilla JavaScript (no build step) |
| Backend | Python 3.12, Flask 3, Gunicorn |
| AWS SDK | boto3 |
| Database | Amazon DynamoDB (AWS mode), SQLite (demo mode) |
| Notifications | Amazon SNS direct SMS |
| Infrastructure | AWS CloudFormation (VPC, subnets, IGW, route table, security group, DynamoDB, IAM, EC2) |
| Hosting | Amazon EC2 (Amazon Linux 2023), nginx as the public server, systemd |

## Project structure

```
QuickBite/
├── app.py                     Flask app: pages and JSON API
├── config.py                  Settings from environment variables
├── requirements.txt           Runtime dependencies (pinned)
├── requirements-dev.txt       Test dependencies
├── .env.example               Environment template (no secrets)
├── pytest.ini
├── services/
│   ├── order_service.py       Validation, server-side pricing, status rules, notifications
│   ├── student_service.py     Student account validation and lookup
│   ├── menu_service.py        Staff menu management and item validation
│   ├── dynamodb_service.py    DynamoDB storage (AWS mode)
│   ├── demo_store.py          SQLite storage (demo mode), same interface
│   ├── sns_service.py         SMS sending through SNS, never raises
│   ├── menu_data.py           Sample menu
│   └── errors.py              Shared exception types
├── templates/                 Jinja2 pages (base, index, cart, checkout, confirmation, tracking, staff)
├── static/
│   ├── css/style.css          Student styles
│   ├── css/dashboard.css      Staff dashboard styles
│   ├── js/main.js             Shared helpers and cart storage
│   ├── js/student_login.js    Student account login and registration
│   ├── js/student_menu.js     Student menu and live availability
│   ├── js/cart.js             Cart and checkout pages
│   ├── js/tracking.js         Order tracking page
│   ├── js/staff.js            Staff order dashboard
│   ├── js/manage_items.js     Staff menu management
│   └── images/logo.svg
├── scripts/
│   ├── seed_menu.py           Load the sample menu into the active backend
│   ├── make_password_hash.py  Create STAFF_PASSWORD_HASH
│   └── test_aws_connection.py Check AWS access (PASS/FAIL per service)
├── infrastructure/cloudformation/quickbite-stack.yaml
├── deployment/
│   ├── ec2_setup.sh           First-time install on EC2
│   ├── deploy.sh              Redeploy code on EC2
│   ├── quickbite.service      systemd unit (gunicorn)
│   ├── nginx.conf             Minimal nginx main config
│   └── nginx-quickbite.conf   Reverse proxy on port 80
├── tests/
│   ├── test_app.py            Application tests (demo mode)
│   └── test_dynamodb_service.py  DynamoDB tests against a mocked AWS
└── docs/                      Architecture, AWS setup, deployment, troubleshooting, security
```

## Quick start: local demo mode

Requirements: Python 3.10 or newer. No AWS account needed.

```bash
cd QuickBite
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env:
#   APP_MODE=demo
#   SECRET_KEY=<any long random string>
#   STAFF_PASSWORD_HASH=<see next step>

python scripts/make_password_hash.py   # type a staff password; copy the printed line into .env
python scripts/seed_menu.py            # loads the sample menu into instance/quickbite_demo.db
python app.py                          # development server on http://127.0.0.1:5000
```

Open http://127.0.0.1:5000. A yellow banner shows that demo mode is active. Orders are saved in `instance/quickbite_demo.db`, so they survive restarts. Delete that file to reset the data.

Staff dashboard: http://127.0.0.1:5000/staff (log in with the password you hashed).

## AWS mode

AWS mode uses DynamoDB for data and SNS for SMS. Full steps are in [docs/aws_setup.md](docs/aws_setup.md) and [docs/deployment.md](docs/deployment.md). In outline:

1. Choose a region (the default is `ap-south-1`, Mumbai) and check costs.
2. Deploy `infrastructure/cloudformation/quickbite-stack.yaml`. It creates the network, both DynamoDB tables, the IAM role, and the EC2 instance.
3. Seed the menu from your laptop with `APP_MODE=aws python scripts/seed_menu.py` (your own credentials are needed for this step only).
4. On the instance, run `deployment/ec2_setup.sh`, set `STAFF_PASSWORD_HASH` and `SECRET_KEY`, and restart the service.
5. Optionally verify SMS with `python scripts/test_aws_connection.py --sms-test +91XXXXXXXXXX`.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `APP_MODE` | `demo` | `demo` (SQLite) or `aws` (DynamoDB) |
| `SECRET_KEY` | none | Signs session cookies. Required in aws mode. |
| `STAFF_PASSWORD_HASH` | none | Hash of the staff password. Without it, staff login is disabled. |
| `STAFF_SESSION_HOURS` | `8` | Staff session length |
| `AWS_REGION` | `ap-south-1` | Region for DynamoDB and SNS |
| `MENU_TABLE_NAME` / `ORDERS_TABLE_NAME` / `STUDENTS_TABLE_NAME` | `QuickBite-MenuItems` / `QuickBite-Orders` / `QuickBite-Students` | DynamoDB table names |
| `SNS_ENABLED` | `false` | Send SMS notifications |
| `SNS_SMS_SENDER_ID` | blank | Optional sender ID (see docs/aws_setup.md) |
| `TIMEZONE` | `Asia/Kolkata` | Used for order dates and the staff "today" view |
| `DEMO_DB_PATH` | `instance/quickbite_demo.db` | Demo mode database file |
| `SESSION_COOKIE_SECURE` | `false` | Set to `true` only once HTTPS is in place |

## DynamoDB design

**MenuItems**: partition key `item_id` (string). The menu is small, so the app reads it with a Scan.

**Students**: partition key `lookup_key` (string). Accounts and unique phone/college-ID lookup records are written together with a DynamoDB transaction.

**Orders**: partition key `order_id` (string, for example `QB-2026-3F9A1C2B`).
- Tracking one order: `GetItem` on `order_id`.
- Placing an order: `PutItem` with `attribute_not_exists(order_id)`, so an ID can never be overwritten.
- Staff list for one day: `Query` on the global secondary index `ByOrderDate` (partition key `order_date` such as `2026-11-23`, sort key `created_at`). The table is never scanned for staff.
- Student order history: `Query` on `ByStudentPhone` (partition key `student_phone`, sort key `created_at`).
- Status change: `UpdateItem` with `status = :expected`, so two staff members cannot both apply a conflicting change.
- Staff search by name or phone runs over the current day's orders in the application. This is fine for a canteen's daily volume. For a large dataset you would add a GSI on `student_phone`.

## Notifications (SNS)

The app sends SMS directly to the student's phone with `sns:Publish` and `PhoneNumber`. No SNS topic is needed.

- Order placed: `QuickBite: Your order QB-XXXX has been placed successfully. Total: ₹XXX.`
- Marked Ready: `QuickBite: Your order QB-XXXX is ready for pickup. Please collect it from the campus canteen.`

The app says "accepted by SNS" rather than "delivered", because SNS only confirms it accepted the request. Delivery to a handset is not confirmed. See docs/aws_setup.md for sandbox limits, regional rules, and charges.

## Testing

Run the automated tests (no AWS account needed):

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The tests cover student account validation and duplicate checks, menu management and availability, server-side pricing, staff authentication, forward-only status changes, completed-order privacy, SMS failure handling, and DynamoDB behaviour against a mocked AWS.

### Manual checklist

**Student**
- [ ] Login is shown first; invalid and duplicate phone/college IDs show field errors
- [ ] Refreshing keeps the student logged in
- [ ] Skip opens browse-only mode; Add to Cart and Cart/Checkout return to login with a prompt
- [ ] Menu loads, and category filters and search work
- [ ] Add to cart and quantity changes update the cart badge
- [ ] Sold-out items cannot be added; availability changes appear without refreshing
- [ ] Cart totals are correct and checkout is disabled when the cart is empty
- [ ] An order places, shows a confirmation page with an Order ID, and the cart empties
- [ ] Checkout defaults to Pay at Counter; Pay Online selection is saved on the order
- [ ] Tracking ends at Ready for Pickup; completed orders return to the menu and remain in My Account history
- [ ] My Account shows account details and completed order history

**Staff**
- [ ] `/staff` redirects to login when logged out; wrong passwords are rejected
- [ ] Orders appear, and counts and filters match
- [ ] Orders update without a page refresh; completed orders appear in their own filter
- [ ] Payment indicator changes to Paid when staff records payment
- [ ] Manage Items can edit name/price, toggle availability, and add an item
- [ ] Search by order ID, name and phone works
- [ ] Forward status updates work; skipping a step is refused
- [ ] Marking Ready shows the SMS result message

**AWS**
- [ ] `scripts/test_aws_connection.py` passes for STS and all three tables
- [ ] Orders appear in the DynamoDB console after placing one
- [ ] `--sms-test` delivers a message to a verified number (sandbox rules apply)
- [ ] The application URL loads from the public internet on port 80
- [ ] The security group allows SSH only from your IP

## Cleanup (avoid charges)

Delete the CloudFormation stack in the AWS console (CloudFormation → Stacks → QuickBite → Delete). This removes the EC2 instance, security group, VPC, subnets, route table, Internet Gateway, IAM role and instance profile, and all three DynamoDB tables. The tables are set to Delete, so all stored data is removed too. Also delete any key pair you created for SSH and any SNS sandbox phone numbers you no longer need. Full steps: docs/deployment.md.

## Security notes

This is a beginner and demo project. Read [docs/security.md](docs/security.md) before any public use. The main limitations are: a single shared staff password, no rate limiting, no HTTPS by default, and tracking by order ID alone.

## Known limitations

- Student login matches a name and phone number and is for basic identification only; it is not a password or verified identity.
- Pay Online records the student's preference only. The app does not process payments; payment is recorded after staff receives it at pickup.
- Menu images are emoji placeholders. To use photos, add files to `static/images` and set `image_url`.
- SMS is sent through SNS only. Indian SMS sender IDs need registration, and unregistered senders may not be accepted.
- Estimated preparation time is a fixed rule (5 minutes plus 2 per portion, capped at 25), not real kitchen data.
- The application has not been tested with real AWS resources in this build; AWS behaviour is covered by mocked tests and the connectivity script.
