import smtplib
from email.message import EmailMessage
from flask import current_app


def send_email(to_email, subject, body_text):
    """Send an email using SMTP if MAIL_SERVER is configured, or print to terminal."""
    server = current_app.config.get("MAIL_SERVER")
    if server:
        try:
            msg = EmailMessage()
            msg.set_content(body_text)
            msg["Subject"] = subject
            msg["From"] = current_app.config.get("MAIL_DEFAULT_SENDER", "noreply@eduhive.in")
            msg["To"] = to_email

            port = current_app.config.get("MAIL_PORT", 587)
            use_tls = current_app.config.get("MAIL_USE_TLS", True)
            username = current_app.config.get("MAIL_USERNAME")
            password = current_app.config.get("MAIL_PASSWORD")

            with smtplib.SMTP(server, port, timeout=5) as smtp:
                if use_tls:
                    smtp.starttls()
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(msg)
            return True
        except Exception as e:
            current_app.logger.warning(f"Failed to send email via SMTP: {e}. Falling back to terminal.")

    # Fallback: print email clearly to terminal
    print("\n" + "=" * 60)
    print(" [EduHive EMAIL NOTIFICATION]")
    print(f" To: {to_email}")
    print(f" Subject: {subject}")
    print("-" * 60)
    print(body_text)
    print("=" * 60 + "\n")
    return True
