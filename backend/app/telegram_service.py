"""Send messages and documents via the Telegram Bot API."""

import html as _html
import os

import httpx

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

MAX_MSG_LEN = 4000


async def _post(client: httpx.AsyncClient, payload: dict) -> httpx.Response:
    return await client.post(f"{TELEGRAM_API}/sendMessage", json=payload)


async def send_message(chat_id: str, text: str) -> tuple[bool, str]:
    if not TELEGRAM_BOT_TOKEN:
        print(f"[TELEGRAM DEV] No token. To {chat_id}: {text[:100]}")
        return False, "TELEGRAM_BOT_TOKEN not set"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # First attempt: HTML
            r = await _post(client, {
                "chat_id": chat_id,
                "text": text[:MAX_MSG_LEN],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })

            # If Telegram rejects the HTML, retry as plain text
            if r.status_code == 400 and "can't parse entities" in r.text:
                print(f"[TELEGRAM] HTML parse failed, retrying as plain text")
                import re as _re
                # strip any HTML tags from the text for the plain fallback
                plain = _re.sub(r"<[^>]+>", "", text)[:MAX_MSG_LEN]
                # decode the entity escapes so the user sees < >
                plain = (_html.unescape(plain)
                              .replace("&lt;", "<")
                              .replace("&gt;", ">")
                              .replace("&amp;", "&"))
                r = await _post(client, {
                    "chat_id": chat_id,
                    "text": plain,
                    "disable_web_page_preview": True,
                })

        if r.status_code == 200:
            print(f"[TELEGRAM] Sent to {chat_id}")
            return True, ""
        body = r.text[:220]
        print(f"[TELEGRAM ERROR] {r.status_code}: {body}")
        return False, f"Telegram {r.status_code}: {body[:100]}"
    except Exception as e:
        print(f"[TELEGRAM EXCEPTION] {type(e).__name__}: {e}")
        return False, f"{type(e).__name__}: {e}"


async def send_activation_key(chat_id: str, key_value: str,
                              label: str | None = None) -> tuple[bool, str]:
    label_html = f"\n<b>Label:</b> {_html.escape(label)}" if label else ""
    text = (
        f"<b>🎉 Welcome to Assist</b>\n\n"
        f"Your activation key is:\n"
        f"<code>{_html.escape(key_value)}</code>"
        f"{label_html}\n\n"
        f"<b>Next steps:</b>\n"
        f"1. Download Assist-v1.3.zip\n"
        f"2. Unzip, double-click <code>Assist.exe</code>\n"
        f"3. Click \"More info → Run anyway\" on the Windows warning\n"
        f"4. Paste the key above when the activation dialog appears\n\n"
        f"Type /help to see all bot commands."
    )
    return await send_message(chat_id, text)


async def send_onboarding_link(chat_id: str, onboarding_url: str) -> tuple[bool, str]:
    text = (
        f"<b>👋 Welcome to Assist</b>\n\n"
        f"One more step — complete your profile using the link below. "
        f"You'll receive your activation key right here on Telegram.\n\n"
        f'<a href="{_html.escape(onboarding_url)}">Complete onboarding →</a>\n\n'
        f"<i>This link expires in 72 hours.</i>"
    )
    return await send_message(chat_id, text)


async def send_transcript(chat_id: str, transcript: dict) -> tuple[bool, str]:
    segments = transcript.get("segments", [])
    if not segments:
        return await send_message(chat_id, "Transcript is empty.")

    lines = ["<b>📄 Meeting transcript</b>",
             f"<i>{transcript.get('session_started', '?')} → "
             f"{transcript.get('session_ended', '?')}</i>\n"]
    current = "\n".join(lines)

    for seg in segments:
        ts = int(seg.get("t", 0))
        t = _html.escape(str(seg.get("text", "")))
        line = f"<code>{ts//60:02d}:{ts%60:02d}</code> {t}"
        if len(current) + len(line) + 1 > MAX_MSG_LEN:
            ok, err = await send_message(chat_id, current)
            if not ok:
                return False, err
            current = line
        else:
            current += "\n" + line

    if current:
        return await send_message(chat_id, current)
    return True, ""


async def set_commands():
    commands = [
        {"command": "start", "description": "Welcome & onboarding"},
        {"command": "help", "description": "List all commands"},
        {"command": "status", "description": "Your account status & quota"},
        {"command": "profile", "description": "Show your profile"},
        {"command": "transcripts", "description": "Recent meeting transcripts"},
        {"command": "answers", "description": "Interview answer history"},
        {"command": "support", "description": "Contact admin"},
        {"command": "unlink", "description": "Disconnect this chat"},
        {"command": "about", "description": "What Assist does"},
    ]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{TELEGRAM_API}/setMyCommands",
                json={"commands": commands},
            )
        if r.status_code == 200:
            print(f"[TELEGRAM] Registered {len(commands)} bot commands")
        else:
            print(f"[TELEGRAM ERROR] setMyCommands: {r.status_code} {r.text[:120]}")
    except Exception as e:
        print(f"[TELEGRAM EXCEPTION] setMyCommands: {e}")