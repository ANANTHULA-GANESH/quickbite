"""SMS notifications through Amazon SNS (direct SMS to a phone number, no topic needed).

send() returns one of:
  "accepted" : SNS accepted the publish request. This does NOT prove the handset received it.
  "disabled" : SNS_ENABLED is false (normal for local development).
  "failed"   : SNS rejected the request or could not be reached. The order is still saved.
"""
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger("quickbite.notifications")


def mask_phone(phone):
    """Keep only the last 4 digits in logs."""
    return "*" * max(len(phone) - 4, 0) + phone[-4:]


class SmsNotifier:
    def __init__(self, enabled, region=None, sender_id="", client=None):
        self.enabled = enabled
        self.sender_id = sender_id
        self._client = client
        if enabled and self._client is None:
            self._client = boto3.client("sns", region_name=region)

    def send(self, phone, message, context):
        """`context` is the order ID. It is safe to log. Phone numbers are masked."""
        if not self.enabled:
            logger.info("SMS disabled; skipped notification for %s", context)
            return "disabled"

        attributes = {"AWS.SNS.SMS.SMSType": {"DataType": "String", "StringValue": "Transactional"}}
        if self.sender_id:
            attributes["AWS.SNS.SMS.SenderID"] = {"DataType": "String", "StringValue": self.sender_id}
        try:
            response = self._client.publish(
                PhoneNumber=phone, Message=message, MessageAttributes=attributes
            )
            logger.info("SNS accepted SMS for %s to %s (message id %s)",
                        context, mask_phone(phone), response.get("MessageId"))
            return "accepted"
        except (BotoCoreError, ClientError) as exc:
            # Log the exception type only. Error text can echo request details.
            logger.error("SNS publish failed for %s to %s (%s)",
                         context, mask_phone(phone), exc.__class__.__name__)
            return "failed"
