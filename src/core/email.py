import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.core.logging import logger

MAIL_HOST = os.getenv("MAIL_HOST")
MAIL_PORT = int(os.getenv("MAIL_PORT", 465))
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM_ADDRESS = os.getenv("MAIL_FROM_ADDRESS")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "")
# Mailbox that receives user feedback submissions.
FEEDBACK_TO_ADDRESS = os.getenv("FEEDBACK_TO_ADDRESS", "info@voxiin.com")


def send_email(to: str, subject: str, body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{MAIL_FROM_NAME} <{MAIL_FROM_ADDRESS}>"
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL(MAIL_HOST, MAIL_PORT) as server:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.sendmail(MAIL_FROM_ADDRESS, to, msg.as_string())
        logger.info("Email sent to %s (subject: %s)", to, subject)
    except (smtplib.SMTPException, OSError) as e:
        logger.error("Failed to send email to %s: %s", to, e)
        raise smtplib.SMTPException(str(e)) from e
