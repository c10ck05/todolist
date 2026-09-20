"""Email delivery through Resend."""

import resend

from backend.config import MAIL_FROM, RESEND_API_KEY


resend.api_key = RESEND_API_KEY


def send_email(to: str, subject: str, body: str):
    resend.Emails.send(
        {
            "from": MAIL_FROM,
            "to": [to],
            "subject": subject,
            "text": body,
        }
    )
