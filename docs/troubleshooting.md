# Troubleshooting

Start with the logs. On EC2: `journalctl -u quickbite -n 100 --no-pager` (application) and `sudo tail -n 50 /var/log/nginx/error.log` (web server). Locally, the log is in the terminal running `python app.py`.

## Application will not start

**`RuntimeError: SECRET_KEY must be set when APP_MODE=aws`**
The environment file has no `SECRET_KEY`. Generate one with `python3 -c "import secrets;print(secrets.token_hex(32))"` and add it to `/etc/quickbite/quickbite.env`, then `sudo systemctl restart quickbite`.

**`RuntimeError: APP_MODE must be 'demo' or 'aws'.`**
Check the spelling of `APP_MODE` in `.env` or the environment file. It is case-insensitive but must be one of these two values.

**`ModuleNotFoundError: No module named 'flask'` (or boto3, dotenv)**
The virtual environment is missing packages. Activate it and run `pip install -r requirements.txt`. On EC2: `sudo /opt/quickbite/venv/bin/pip install -r /opt/quickbite/requirements.txt`.

**systemd shows `failed` with `status=3`**
Run `journalctl -u quickbite -n 100 --no-pager` to read the Python error. Most often it is a missing environment variable or a missing package.

**Port 8000 or 5000 already in use**
Another process is using the port. Find it with `sudo ss -ltnp | grep 8000` and stop it, or change the port.

## Login problems

**Staff login says "not configured yet"**
`STAFF_PASSWORD_HASH` is empty. Create a hash with `scripts/make_password_hash.py` and set it (see [deployment.md](deployment.md) step 4). Restart the service after editing the file.

**"Incorrect password" with the right password**
- Make sure the hash was copied in full, including the quotes. It contains `$` characters, so wrap the value in single quotes.
- If you regenerated the hash, the old password no longer works. Only the newest hash is valid.
- Do not paste the password into the environment file. Only the hash belongs there.

**Logged out after a few hours**
This is expected. Staff sessions last `STAFF_SESSION_HOURS` (default 8). Sessions are also invalidated when `SECRET_KEY` changes. If `SECRET_KEY` is not set in demo mode, the app generates a temporary key at each start, so restarting demo mode logs everyone out.

## Ordering problems

**"Your cart is empty" or "Quantity must be..." errors**
The browser sent data the server rejected. Refresh the cart page; items that no longer exist are removed automatically. Quantities must be between 1 and 10.

**"X is currently unavailable"**
The item's `available` flag is `false` in the menu table. Set it to `true` in the DynamoDB console (MenuItems → item → edit) or run the seed script again after editing `services/menu_data.py`.

**"Enter a valid 10-digit mobile number"**
Indian numbers are accepted as 10 digits (for example `9876543210`), or with `+91` or `91` in front. Other countries need a full international number in `+CC...` format, and you may need to change `DEFAULT_COUNTRY_CODE` in `services/order_service.py`.

**Menu shows "Could not load the menu"**
The `/api/menu` request failed. Check `curl -s http://127.0.0.1/api/menu` on the instance. If it returns an error, read the application log. Usually DynamoDB permissions or the table name are wrong (see AWS errors below).

## AWS and DynamoDB errors

**`NoCredentialsError` when running scripts on EC2**
The instance profile is not attached. In **EC2 → Instances → select instance → Actions → Security → Modify IAM role**, choose `QuickBite-EC2-InstanceProfile`. Wait a minute, then retry. Then run `/opt/quickbite/venv/bin/python /opt/quickbite/scripts/test_aws_connection.py` again. The instance metadata service uses IMDSv2 here, so plain curl requests to it need a session token; boto3 handles that automatically.

**`AccessDeniedException` on DynamoDB**
The role's inline policy does not allow the action. Check `QuickBite-LeastPrivilege` in IAM. The app needs read/update access on menu items, transactional writes and reads on student accounts, and GetItem, PutItem, UpdateItem and Query on orders. If you changed table names, the policy resources must match the stack.

**`ResourceNotFoundException: Requested resource not found`**
A table name in the environment file does not match a real table. Compare `MENU_TABLE_NAME`, `ORDERS_TABLE_NAME` and `STUDENTS_TABLE_NAME` with the stack Outputs, and check `AWS_REGION` matches the region of the stack.

**Staff list is empty but orders exist**
The staff view shows the current day in the time zone set by `TIMEZONE` (default `Asia/Kolkata`). Orders are grouped by the date they were placed in that zone, so an order placed just after midnight IST appears under the new day. Check the server clock with `timedatectl` if the dates look wrong.

**`ValidationException` about the index**
The `ByOrderDate` index is missing or still being created. Check **DynamoDB → Tables → QuickBite-Orders → Indexes**. A new index can take a few minutes to become ACTIVE.

## SMS problems

**Notification shows "disabled"**
`SNS_ENABLED` is `false`. This is normal in demo mode. Set `SNS_ENABLED=true` on EC2 and restart.

**Notification shows "failed" in the staff toast**
The order and status were still saved. Read the log line `SNS publish failed for QB-... (ClientError)`. Common causes:
- The number is not verified while the account is in the SMS sandbox. Verify it in **SNS → Text messaging**, or request production access.
- The IAM role lacks `sns:Publish`. Check the inline policy.
- The region does not support SMS for that country, or the sender ID is not registered.
- The monthly spend limit has been reached. Check **SNS → Text messaging → Account spend limit**.

**"accepted" but the phone received nothing**
SNS accepted the request, but the carrier did not deliver it. Check the delivery status in **SNS → Text messaging → Delivery status logging** (set this up if you need it), and check the phone's spam or blocked messages folder.

## nginx and networking

**Browser cannot reach the site**
Check these in order:
1. `systemctl status nginx` and `systemctl status quickbite` both show active.
2. `curl -s http://127.0.0.1/healthz` on the instance returns `ok`. If not, nginx is not proxying. Run `sudo nginx -t`.
3. The security group allows TCP 80 from `0.0.0.0/0`.
4. The instance is in `QuickBite-Public-Subnet-1` and has a public IP.
5. The route table `QuickBite-Public-RT` has `0.0.0.0/0` to the Internet Gateway.
6. You are using `http://`, not `https://`.

**`nginx: [emerg] ... bind() to 0.0.0.0:80 failed`**
Another web server is using port 80. Stop it (`sudo systemctl stop httpd` if Apache is installed) and restart nginx.

**`duplicate default server` or `conflicting server name`**
The installer replaces `/etc/nginx/nginx.conf` with the QuickBite version. If you added other sites, move them into `/etc/nginx/conf.d/` with a unique `server_name` and remove the `default_server` flag from all but one.

**502 Bad Gateway**
nginx is running but gunicorn is not. Check `journalctl -u quickbite`, fix the error, and restart the service.

**SSH times out**
Your public IP has changed since the stack was created. Update the rule for port 22 in `QuickBite-SG` to your current address (see [aws_setup.md](aws_setup.md) section 6).

**Permission denied (publickey) on SSH**
Use the right key file and user (`ec2-user` for Amazon Linux). Check the key's permissions: `chmod 400 quickbite-key.pem`. If the instance was launched without a key pair, you must connect another way (Session Manager) or redeploy with a key pair.

## CloudFormation problems

**`ROLLBACK_COMPLETE` on create**
Open the stack's Events tab and read the first failed resource. Common causes: an invalid CIDR, a parameter pattern rejected, or the AMI parameter not available in the region. Fix the parameter and create the stack again (delete the failed stack first).

**`CAPABILITY_NAMED_IAM` error**
Tick the IAM acknowledgement box in the console, or add `--capabilities CAPABILITY_NAMED_IAM` to the CLI command.

**Stack delete stuck on DynamoDB or the VPC**
A resource was created outside the stack (for example an extra ENI or security group attached to the VPC). Delete that resource manually, then delete the stack again.

## Local development

**Demo orders disappeared**
Demo data is kept in `instance/quickbite_demo.db` and survives restarts. Deleting that file resets everything. If `DEMO_DB_PATH` changed, the app is now reading a new, empty file.

**Tests fail with ModuleNotFoundError**
Run tests from the project folder with `python -m pytest`, after installing `requirements-dev.txt`.

**Pages look unstyled**
Check the browser's developer tools for 404 errors on `/static/...`. Run the app from the project folder so the static path resolves.

## Getting more help

Collect the output of `journalctl -u quickbite -n 100 --no-pager` and the stack's Events tab (with secrets removed). Never paste the environment file, password hashes, or SECRET_KEY into a support request.
