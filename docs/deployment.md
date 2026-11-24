# Deployment Guide (EC2)

Prerequisites: the CloudFormation stack `QuickBite` reached `CREATE_COMPLETE` (see [aws_setup.md](aws_setup.md)), and you have the instance's public IP or DNS from the Outputs tab.

## 1. Seed the menu

From your laptop (using your own AWS credentials with `dynamodb:PutItem` on the menu table):

```bash
cd QuickBite
source venv/bin/activate
APP_MODE=aws AWS_REGION=ap-south-1 python scripts/seed_menu.py
```

Expected output: `Seeded 12 menu items (APP_MODE=aws).` Confirm in **DynamoDB → Tables → QuickBite-MenuItems → Explore items**.

## 2. Get the code onto the instance

Choose one:

- **Option A, the stack's `AppSourceUrl`.** Create a tarball of the project (`tar -czf quickbite.tar.gz --exclude venv --exclude instance --exclude .venv-test -C .. QuickBite`), host it at an HTTPS URL such as a pre-signed S3 link, and pass it as `AppSourceUrl` when creating the stack. The instance then installs everything on first boot.
- **Option B, copy with scp (recommended for first deployment).**

```bash
scp -i quickbite-key.pem -r QuickBite ec2-user@<PublicIp>:/home/ec2-user/
```

## 3. Run the installer on the instance

```bash
ssh -i quickbite-key.pem ec2-user@<PublicIp>
cd ~/QuickBite
sudo bash deployment/ec2_setup.sh
```

The script:
- installs Python, pip, nginx and rsync with dnf
- creates the `quickbite` system user
- copies the app to `/opt/quickbite` and builds a virtual environment there
- creates `/etc/quickbite/quickbite.env` with a generated `SECRET_KEY` and `APP_MODE=aws`
- installs the systemd service `quickbite` and the nginx configuration
- starts both services

It is safe to run again. It keeps the existing environment file.

## 4. Set the staff password

On the instance, generate the hash (the password is typed privately):

```bash
cd /opt/quickbite
sudo -u quickbite /opt/quickbite/venv/bin/python scripts/make_password_hash.py
```

Copy the printed `STAFF_PASSWORD_HASH='...'` line, then edit the environment file:

```bash
sudo nano /etc/quickbite/quickbite.env
# replace the STAFF_PASSWORD_HASH='' line with the printed line
sudo systemctl restart quickbite
```

Until this is done, staff login shows a "not configured" message. Students can still order.

## 5. Verify the installation

```bash
systemctl status quickbite --no-pager        # should show "active (running)"
systemctl status nginx --no-pager            # should show "active (running)"
journalctl -u quickbite -n 50 --no-pager     # application logs
curl -s http://127.0.0.1/healthz             # should print: ok
/opt/quickbite/venv/bin/python /opt/quickbite/scripts/test_aws_connection.py
```

The last command should show PASS for STS and both DynamoDB tables. If it does not, check that the instance profile is attached and see [troubleshooting.md](troubleshooting.md).

## 6. Access the application

Open the Outputs `ApplicationUrl` (for example `http://ec2-xx-xx-xx-xx.ap-south-1.compute.amazonaws.com`) or `http://<PublicIp>` in a browser.

How the request reaches the app:
1. The browser connects to the public IP or DNS name on port 80.
2. The **security group** `QuickBite-SG` allows TCP 80 from anywhere.
3. The **route table** `QuickBite-Public-RT` sends internet traffic to the **Internet Gateway**, which makes the subnet public.
4. nginx receives the request and proxies it to gunicorn on 127.0.0.1:8000.
5. Flask answers, reading and writing DynamoDB through the instance profile.

**HTTP only.** The app is not HTTPS-secured in this version. Do not enter real passwords on a public network until HTTPS is configured (section 8).

Public IP note: the public IP changes if the instance is stopped and started. Use the DNS name or an Elastic IP for a stable address (an Elastic IP may incur a charge while not attached to a running instance).

## 7. Updating the application

After changing code locally, copy the changed project to the instance and run:

```bash
sudo bash ~/QuickBite/deployment/deploy.sh
```

It syncs the code, updates dependencies, and restarts the service. It does not change `/etc/quickbite/quickbite.env` or any data.

## 8. Adding HTTPS later

1. Point a domain name at the instance (Route 53 or your DNS provider).
2. Install certbot and obtain a certificate, for example with `sudo dnf install certbot python3-certbot-nginx` and then `sudo certbot --nginx -d your.domain`. Follow certbot's prompts.
3. Open TCP 443 in `QuickBite-SG` (the template does not open it).
4. Set `SESSION_COOKIE_SECURE=true` in `/etc/quickbite/quickbite.env` and restart the service.
5. Make sure nginx redirects port 80 to HTTPS.

## 9. Cleanup (avoid charges)

1. Delete the CloudFormation stack: **CloudFormation → Stacks → QuickBite → Delete**. This removes all stack resources, including both DynamoDB tables and their data.
2. Delete any Elastic IP you allocated separately.
3. Delete the key pair in **EC2 → Key Pairs** if you no longer need it.
4. Remove SNS sandbox phone numbers and check the **Billing** dashboard a few days later.

If stack deletion fails, read the stack's Events tab. A common cause is a resource changed outside CloudFormation. Remove that resource manually, then retry the delete.
