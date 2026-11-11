"""Email delivery via Brevo HTTP API (works on Render — port 443)."""

import os

import httpx

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_FROM_EMAIL = os.environ.get(
    "BREVO_FROM_EMAIL", "ananthathehacker@gmail.com"
)
BREVO_FROM_NAME = os.environ.get("BREVO_FROM_NAME", "Assist")


async def _send(to_email: str, subject: str, html_body: str) -> bool:
    if not BREVO_API_KEY:
        print(f"[MAIL DEV] To: {to_email} | {subject}\n{html_body}")
        return False
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": BREVO_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "sender": {
                        "email": BREVO_FROM_EMAIL,
                        "name": BREVO_FROM_NAME,
                    },
                    "to": [{"email": to_email}],
                    "subject": subject,
                    "htmlContent": html_body,
                },
            )
        if r.status_code in (200, 201, 202):
            print(f"[MAIL] Sent '{subject}' to {to_email} (brevo)")
            return True
        print(f"[MAIL ERROR] Brevo HTTP {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        print(f"[MAIL ERROR] Brevo exception: {e}")
        return False


# --- keep the same three public functions ---
async def send_otp_email(to_email: str, otp_code: str) -> bool:
    return await _send(
        to_email, "Assist Admin — Your Login Code",
        f'<div style="font-family:sans-serif;padding:20px;">'
        f'<h2>Admin Login</h2><p>Your code:</p>'
        f'<p style="font-size:28px;font-weight:bold;letter-spacing:4px;'
        f'background:#f0f0f0;padding:12px;display:inline-block;border-radius:6px;">'
        f'{otp_code}</p><p>Expires in 10 minutes.</p></div>',
    )


async def send_activation_key_email(to_email, key_value, label=None):
    label_html = f"<p><em>Label: {label}</em></p>" if label else ""
    return await _send(
        to_email, "Your Assist Activation Key",
        f'<div style="font-family:sans-serif;padding:20px;">'
        f'<h2>Welcome to Assist</h2><p>Your activation key:</p>'
        f'<p style="font-size:20px;font-weight:bold;letter-spacing:2px;'
        f'background:#f0f0f0;padding:12px;display:inline-block;border-radius:6px;">'
        f'{key_value}</p>{label_html}'
        f'<p>Paste this into the Assist desktop app.</p></div>',
    )


async def send_transcript_email(to_email: str, transcript: dict) -> bool:
    import html as _html
    rows = []
    for seg in transcript.get("segments", []):
        t = _html.escape(str(seg.get("text", "")))
        ts = seg.get("t", 0)
        rows.append(
            f'<tr><td style="color:#888;font-family:monospace;'
            f'padding:4px 12px 4px 0;white-space:nowrap;">'
            f'{int(ts)//60:02d}:{int(ts)%60:02d}</td>'
            f'<td style="padding:4px 0;">{t}</td></tr>'
        )
    body = (
        '<div style="font-family:sans-serif;padding:20px;max-width:800px;">'
        '<h2>Your meeting transcript</h2>'
        f'<p style="color:#666;">{transcript["session_started"]} → '
        f'{transcript["session_ended"]}</p>'
        '<table style="border-collapse:collapse;font-size:14px;line-height:1.5;">'
        + "".join(rows) + '</table></div>'
    )
    return await _send(to_email, "Your Assist meeting transcript", body)