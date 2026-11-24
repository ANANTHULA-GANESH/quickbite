# Security Notes

QuickBite is built as a learning and pilot project. It applies sound basics, but it is not ready for unrestricted public use with real students' personal data without the changes listed in section 4.

## 1. Controls in place

| Area | Control |
|---|---|
| Prices | The server reads prices from the menu store. Any price in the request is ignored (tested). |
| Order integrity | Order IDs are generated on the server. Writes use conditional checks so an existing order cannot be overwritten. |
| Status changes | Only staff can change status. Changes are forward-only, one step at a time, and conditional on the current status. |
| Staff authentication | Password checked against a salted hash (Werkzeug, scrypt by default). The plain password is never stored. |
| Sessions | Staff session cookie is HTTP-only and SameSite=Lax. It lasts `STAFF_SESSION_HOURS`. `SESSION_COOKIE_SECURE` can be enabled once HTTPS is in place. |
| Staff API | `/api/staff/*` returns 401 without a valid session. Staff pages redirect to login. |
| Student ordering | Account creation validates 10-digit phone and college ID values; orders use the logged-in account rather than browser-supplied identity fields. |
| CSRF on JSON APIs | Staff updates send JSON with `Content-Type: application/json`. Browsers require a CORS preflight for that, and the app sends no CORS headers, so other websites cannot make these requests with a victim's cookie. The login form itself is not CSRF-protected (see section 3). |
| Input validation | Name, phone, student ID, quantities, cart size, status values and date format are all validated on the server. |
| Privacy in public views | `/api/orders/<id>` never returns the phone number. Logs contain the order ID and the last 4 digits of a phone number only. SNS error text is not logged, because it can echo request data. |
| Headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, and `Cache-Control: no-store` on staff pages. |
| Jinja output | Templates escape output by default. The browser builds card content with `textContent`, not `innerHTML`, so menu or customer text is not executed as HTML. |
| AWS credentials | No keys in the code, the template, or the environment file. EC2 uses an instance profile with temporary credentials. |
| IAM | The role allows menu reads and updates, student account reads/transactional writes, order reads/writes/queries, and `sns:Publish`. |
| Network | Only port 80 is open to the world. SSH is limited to one IP. Gunicorn listens on localhost only, behind nginx. |
| Instance metadata | IMDSv2 is required (`HttpTokens: required`). |
| Data at rest | DynamoDB tables use server-side encryption. |
| Secrets in the repo | `.gitignore` excludes `.env`, databases and key files. |

## 2. Known limitations (beginner level)

1. **One shared staff password.** Everyone who knows it has full staff access, and there is no audit trail of who changed a status. Production needs individual accounts (for example Amazon Cognito or the canteen's existing identity provider) and role-based access.
2. **Student login is not identity verification.** The current requested flow matches only a name and phone number, with no password or OTP. Do not treat it as secure authentication for personal or sensitive data.
3. **No rate limiting.** Staff/student login and order tracking can be tried repeatedly. Production needs rate limiting at nginx (`limit_req`) or AWS WAF, and account lockout for login.
4. **Login form has no CSRF token.** A malicious page could make a logged-in staff member's browser submit the login form, which signs that browser in as staff. It cannot read data or change orders directly. Adding Flask-WTF or a per-form token fixes this.
5. **Order ID is the tracking token.** Anyone with an order ID can see the student's first name, the items and the status. IDs have 32 random bits, which is hard to guess but not impossible to brute-force without rate limiting. Production should use longer random IDs or an access token sent to the student's phone.
6. **HTTP only.** Traffic, including the staff password, is unencrypted in transit. Do not use the staff login on public Wi-Fi until HTTPS is configured (see deployment.md section 8).
7. **Personal data.** Names, phone numbers and college IDs are stored in the configured database. Your institution may have data protection obligations (for example India's Digital Personal Data Protection Act, 2023). Decide what you collect, how long you keep it, and how students can request deletion. The stack's tables use `DeletionPolicy: Delete`, which suits a learning project but not a live system (change to `Retain` and set a TTL or retention job for production).
8. **No payment security.** The app takes no payments, so PCI scope is avoided. Adding online payment would require a payment provider and a new security review.
9. **Dependencies.** Versions are pinned, but there is no automated vulnerability scanning. Run `pip-audit` periodically.
10. **Error detail.** Unexpected errors return generic messages, but the app has no central error monitoring. Add CloudWatch Logs or a similar tool before production.

## 3. Staff password guidance

- Use at least 10 characters. The setup script enforces this.
- Do not reuse a password from another service.
- Rotate it when staff change. To rotate: run `make_password_hash.py` again, update `STAFF_PASSWORD_HASH`, and restart the service. Old sessions remain valid until they expire, so restart the service to end them at once.
- Never write the password into code, a chat, a ticket or the template.

## 4. What production would need

- Individual staff accounts with MFA, and an audit log of status changes (for example a `status_history` list on each order).
- HTTPS everywhere, with HSTS, and `SESSION_COOKIE_SECURE=true`.
- Rate limiting on login and tracking, and a CSRF token on all forms.
- Stronger order access tokens, and an SMS or OTP option for tracking.
- A private subnet for the application tier with an Application Load Balancer in public subnets, and a second Availability Zone. This project keeps everything in one public subnet to stay simple and cheap; the subnet design is explained in architecture.md.
- Retention rules for personal data, `DeletionPolicy: Retain` on tables, and point-in-time recovery enabled.
- Monitoring and alarms (CloudWatch alarms for 5xx errors, failed SNS publishes and DynamoDB throttling), and a tested restore procedure.
- A dependency scanning step in the build, and regular OS patching (for example Systems Manager Patch Manager).
- Demo mode must not run in production. Use `APP_MODE=aws` only, so no local SQLite data is kept on the server.

## 5. Reporting a problem

If you find a security issue in this project, do not post exploit details publicly. Fix the code path, rotate any credentials that could have been exposed, and document the change.
