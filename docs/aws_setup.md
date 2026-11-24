# AWS Setup Guide

This guide explains what the CloudFormation template creates, what you must do yourself, and how to check each step. Console labels can change slightly over time. If a button name differs, look for the nearest match.

## 1. What is automated and what is manual

| Resource | Created by | Notes |
|---|---|---|
| VPC, both subnets, IGW, attachment, route table, route, associations | CloudFormation | Automatic |
| Security group (HTTP 80, SSH 22 from your IP) | CloudFormation | Automatic |
| DynamoDB `QuickBite-MenuItems`, `QuickBite-Orders` (with `ByOrderDate` index), and `QuickBite-Students` | CloudFormation | Automatic |
| IAM role, inline least-privilege policy, instance profile | CloudFormation | Automatic |
| EC2 instance with user data | CloudFormation | Automatic; the app installs on first boot if you give an `AppSourceUrl`, otherwise you run `ec2_setup.sh` |
| Menu data | You run `scripts/seed_menu.py` | Manual, once |
| Staff password hash and secret key | You, on the server | Manual; never stored in the template |
| SNS SMS sandbox verification and any production access | You | Manual (section 4) |
| EC2 key pair for SSH | You, optional | Manual (section 5) |
| Budget alert | You | Recommended (section 6) |

## 2. Prerequisites

- An AWS account with a user or role that can use CloudFormation, EC2, DynamoDB, IAM and SNS. Use your administrator user only for deployment. Do not give the application any broad permissions.
- Choose a region. The default is `ap-south-1` (Mumbai). Confirm that EC2 t3.micro, DynamoDB and SNS SMS are available there.
- Your public IP address. Open https://checkip.amazonaws.com and note the address. You will enter it as `x.x.x.x/32` for SSH.

## 3. Deploy the stack (console)

1. Sign in and switch to your chosen region (top-right).
2. Open **CloudFormation → Stacks → Create stack → With new resources (standard)**.
3. Choose **Upload a template file** and select `infrastructure/cloudformation/quickbite-stack.yaml`. Click **Next**.
4. Stack name: `QuickBite`. Fill in the parameters:
   - `SshAllowedCidr`: your IP with `/32`, for example `203.0.113.25/32`. Required.
   - `KeyPairName`: leave blank, or the name of a key pair you created (section 5).
   - `InstanceType`: `t3.micro`.
   - `AppSourceUrl`: blank, unless you have an HTTPS link to a tarball of the project.
   - `SmsEnabled`: `true` if you want SMS, otherwise `false`.
   - Leave the network CIDRs and table names at their defaults.
5. Click **Next** twice. On the review page, tick **I acknowledge that AWS CloudFormation might create IAM resources with custom names**, then **Submit**.
6. Wait for `CREATE_COMPLETE` (about 3 to 5 minutes).
7. Open the **Outputs** tab. Note `InstanceId`, `PublicIp`, `ApplicationUrl`, and the table names.

### Optional: deploy with the AWS CLI

```bash
aws cloudformation deploy \
  --region ap-south-1 \
  --stack-name QuickBite \
  --template-file infrastructure/cloudformation/quickbite-stack.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides SshAllowedCidr=203.0.113.25/32 InstanceType=t3.micro SmsEnabled=true

aws cloudformation describe-stacks --region ap-south-1 --stack-name QuickBite --query "Stacks[0].Outputs" --output table
```

### Verify the infrastructure

- **VPC**: VPC console → `QuickBite-VPC` exists with CIDR 10.0.0.0/16.
- **Route table**: `QuickBite-Public-RT` has a route `0.0.0.0/0` to `QuickBite-IGW`, and is associated with `QuickBite-Public-Subnet-1`.
- **Security group**: `QuickBite-SG` allows TCP 80 from `0.0.0.0/0` and TCP 22 only from your IP.
- **DynamoDB**: all three tables are ACTIVE, and `QuickBite-Orders` has the `ByOrderDate` and `ByStudentPhone` indexes.
- **IAM**: role `QuickBite-EC2-Role` has the inline policy `QuickBite-LeastPrivilege`, and the instance profile is attached to the instance (EC2 → instance → Security tab).

## 4. SNS SMS setup

Direct SMS is sent with `sns:Publish` and a phone number. You do not need an SNS topic.

1. **Check the SMS sandbox.** Open **SNS → Mobile → Text messaging (SMS)**. A new account starts in the sandbox, which only sends to phone numbers you verify.
2. **Verify test numbers (sandbox only).** Click **Add phone number**, choose the country, enter the number and the verification code you receive. Only verified numbers receive messages in the sandbox.
3. **Set a monthly spending limit.** In the same page, set **Account spend limit** (for example USD 5 for a learning project). This caps charges.
4. **Request production access** when you are ready for real students. Use the request form in the same page. Approval is needed before messages go to unverified numbers.
5. **Indian rules.** Messages to Indian numbers need a registered sender ID and template under the telecom regulator (DLT) rules. Without registration, messages may be blocked or not accepted. For a pilot, keep `SNS_SMS_SENDER_ID` blank and test with verified numbers. Check the current SNS documentation for the latest country requirements before going live.
6. **Unicode and cost.** The ₹ symbol is outside the standard GSM character set, so SMS messages are sent as Unicode. Each message segment then holds fewer characters, and a message may cost more. To reduce cost, you can change the text to "Rs." in `services/order_service.py`.
7. **Verify.** Run `python scripts/test_aws_connection.py --sms-test +91XXXXXXXXXX` on the instance. "accepted" means SNS took the request. Confirm delivery on the handset.

## 5. EC2 key pair (optional)

Session Manager or a key pair are both possible. Key pairs are simpler for this project.

1. **EC2 → Network & Security → Key Pairs → Create key pair.**
2. Name: `quickbite-key`. Type: RSA. Format: `.pem` (macOS, Linux, Windows with OpenSSH) or `.ppk` (PuTTY).
3. Download and store the file securely. You cannot download it again.
4. Enter `quickbite-key` in the `KeyPairName` parameter when you create or update the stack.

Connect with: `ssh -i quickbite-key.pem ec2-user@<PublicIp>` (Amazon Linux user is `ec2-user`).

If you launch without a key pair, you can still connect with **Session Manager** if you add the managed policy `AmazonSSMManagedInstanceCore` to the role. That policy is not in the least-privilege template; add it only if you choose this route.

## 6. Restrict SSH and set alarms

- **SSH source.** The security group allows SSH only from `SshAllowedCidr`. If your home IP changes, edit the rule: **EC2 → Security Groups → QuickBite-SG → Edit inbound rules**, and update the source for port 22. Do not change it to 0.0.0.0/0.
- **Billing alert.** Open **Billing and Cost Management → Budgets → Create budget**. Choose a template such as "Zero spend budget" or a monthly cost budget of your choice, and add your email. This warns you if charges appear.

## 7. Cost notes

Typical monthly costs for a pilot in Mumbai are: one t3.micro EC2 instance (free-tier eligible for new accounts in some cases), DynamoDB on-demand (very low for a canteen's volume), SNS SMS per message (varies by country and sender type), and data transfer. Costs change; check the AWS pricing pages. The stack has no NAT gateway and no load balancer, which keeps costs low.

## 8. After setup

Continue with [deployment.md](deployment.md) to install the application on the instance.
