"""Async SMTP email delivery for OTP codes and activation keys."""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from .config import (
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)


async def _send(to_email: str, subject: str, html_body: str) -> bool:
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[MAIL DEV] To: {to_email} | Subject: {subject}\n{html_body}")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            start_tls=True,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
        )
        print(f"[MAIL] Sent '{subject}' to {to_email}")
        return True
    except Exception as e:
        print(f"[MAIL ERROR] Failed to send to {to_email}: {e}")
        return False


async def send_otp_email(to_email: str, otp_code: str) -> bool:
    return await _send(
        to_email,
        "Assist Admin — Your Login Code",
        f"""<div style="font-family:sans-serif;padding:20px;">
            <h2>Admin Login</h2>
            <p>Your one-time password is:</p>
            <p style="font-size:28px;font-weight:bold;letter-spacing:4px;
                      background:#f0f0f0;padding:12px;display:inline-block;
                      border-radius:6px;">{otp_code}</p>
            <p>This code expires in 10 minutes.</p>
        </div>""",
    )


async def send_activation_key_email(
    to_email: str, key_value: str, label: str | None = None
) -> bool:
    return await _send(
        to_email,
        "Your Assist Activation Key",
        f"""<div style="font-family:sans-serif;padding:20px;">
            <h2>Welcome to Assist</h2>
            <p>Your activation key is:</p>
            <p style="font-size:20px;font-weight:bold;letter-spacing:2px;
                      background:#f0f0f0;padding:12px;display:inline-block;
                      border-radius:6px;">{key_value}</p>
            {f'<p><em>Label: {label}</em></p>' if label else ''}
            <p>Enter this key in the Assist desktop app to activate it.</p>
        </div>""",
    )
async def send_transcript_email(to_email: str, transcript: dict) -> bool:
    """Send a formatted meeting transcript."""
    import html as _html
    rows = []
    for seg in transcript.get("segments", []):
        t = _html.escape(str(seg.get("text", "")))
        ts = seg.get("t", 0)
        mm = int(ts // 60)
        ss = int(ts % 60)
        rows.append(
            f'<tr><td style="color:#888;font-family:monospace;'
            f'padding:4px 12px 4px 0;vertical-align:top;white-space:nowrap;">'
            f'{mm:02d}:{ss:02d}</td>'
            f'<td style="padding:4px 0;">{t}</td></tr>'
        )
    body = (
        '<div style="font-family:sans-serif;padding:20px;max-width:800px;">'
        '<h2>Your meeting transcript</h2>'
        f'<p style="color:#666;">{transcript["session_started"]} → '
        f'{transcript["session_ended"]}</p>'
        '<table style="border-collapse:collapse;font-size:14px;line-height:1.5;">'
        + "".join(rows) +
        '</table>'
        '<p style="color:#888;font-size:12px;margin-top:24px;">'
        'Sent by Assist. Reply to this email if you need help.</p>'
        '</div>'
    )
    return await _send(to_email, "Your Assist meeting transcript", body)