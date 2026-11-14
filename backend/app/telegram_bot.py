"""Telegram command dispatcher and support channel for Assist."""

import html
import os

from . import db
from .telegram_service import send_message, send_onboarding_link, send_transcript

ADMIN_PASSWORD = os.environ.get("ASSIST_ADMIN_PASSWORD", "")
SUPPORT_CONTACT = os.environ.get("ASSIST_SUPPORT_CONTACT", "ananthathehacker@gmail.com")


async def handle_update(update: dict):
    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    text = (message.get("text") or "").strip()
    chat_id = str((message.get("chat") or {}).get("id", ""))
    user_name = (message.get("from") or {}).get("first_name") or "there"
    if not chat_id:
        return
    if text.startswith("/register_admin"):
        await handle_register_admin(chat_id, text)
    elif text == "/inbox":
        await handle_inbox(chat_id)
    elif text.startswith("/reply "):
        await handle_reply(chat_id, text)
    elif text.startswith("/thread "):
        await handle_thread_view(chat_id, text)
    elif text.startswith("/broadcast "):
        await handle_broadcast(chat_id, text)
    elif text == "/users":
        await handle_users(chat_id)
    elif text.startswith("/start"):
        await handle_start(chat_id, text, user_name)
    elif text == "/help":
        await handle_help(chat_id, db.is_admin_chat(chat_id))
    elif text == "/status":
        await handle_status(chat_id)
    elif text == "/transcripts":
        await handle_transcripts(chat_id)
    elif text.startswith("/transcript "):
        await handle_transcript_detail(chat_id, text)
    elif text == "/answers":
        await handle_answers(chat_id)
    elif text == "/profile":
        await handle_profile(chat_id)
    elif text == "/support":
        await handle_support(chat_id)
    elif text == "/unlink":
        await handle_unlink(chat_id)
    elif text == "/about":
        await handle_about(chat_id)
    elif text and not text.startswith("/"):
        if db.is_admin_chat(chat_id):
            await send_message(chat_id, "Use /reply <thread_id> <message> to reply.")
        else:
            from .support import relay_user_message
            await relay_user_message(chat_id, text)
    elif text.startswith("/"):
        await send_message(chat_id, f"Unknown command: <code>{html.escape(text[:30])}</code>")


async def handle_register_admin(chat_id: str, text: str):
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await send_message(
            chat_id,
            "Usage: <code>/register_admin &lt;ADMIN_PASSWORD&gt;</code>\n\n"
            "The password is <code>ASSIST_ADMIN_PASSWORD</code> from your backend env."
        )
        return

    password = parts[1].strip()
    if not ADMIN_PASSWORD or password != ADMIN_PASSWORD:
        await send_message(chat_id, "❌ Wrong password.")
        return

    db.register_admin_chat(chat_id, "admin")
    await send_message(
        chat_id,
        "✅ You are now registered as an admin.\n\n"
        "Commands:\n"
        "<b>/inbox</b> — pending user messages\n"
        "<b>/reply &lt;thread_id&gt; &lt;text&gt;</b> — reply to user\n"
        "<b>/thread &lt;thread_id&gt;</b> — view full conversation\n"
        "<b>/broadcast &lt;text&gt;</b> — send to all users\n"
        "<b>/users</b> — list all users"
    )


async def handle_inbox(chat_id):
    if not db.is_admin_chat(chat_id):
        await send_message(chat_id, "Admin only. Use /register_admin first.")
        return
    threads = db.list_support_threads()
    if not threads:
        await send_message(chat_id, "Inbox is empty.")
        return
    lines = ["<b>Support inbox</b>\n"]
    for thread in threads[:15]:
        label = db.get_key_label_by_chat_id(thread["user_chat_id"]) or thread["user_chat_id"]
        unread = thread["unread"] or 0
        lines.append(f"<b>{html.escape(str(label)[:30])}</b> ({unread} unread)\n"
                     f"<i>{html.escape((thread['last_text'] or '')[:50])}</i>\n"
                     f"<code>/reply {thread['thread_id']} &lt;text&gt;</code>")
    await send_message(chat_id, "\n\n".join(lines))


async def handle_thread_view(chat_id, text):
    if not db.is_admin_chat(chat_id):
        await send_message(chat_id, "Admin only.")
        return
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await send_message(chat_id, "Usage: /thread <thread_id>")
        return
    from .support import format_thread_for_admin
    thread_id = parts[1].strip()
    db.mark_thread_read(thread_id, chat_id)
    await send_message(chat_id, format_thread_for_admin(thread_id))


async def handle_reply(chat_id, text):
    if not db.is_admin_chat(chat_id):
        await send_message(chat_id, "Admin only.")
        return
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await send_message(chat_id, "Usage: /reply <thread_id> <message>")
        return
    from .support import admin_reply_to_thread
    ok, error = await admin_reply_to_thread(chat_id, parts[1], parts[2].strip())
    await send_message(chat_id, f"{'Sent' if ok else 'Error: ' + error}")
    if ok:
        db.mark_thread_read(parts[1], chat_id)


async def handle_broadcast(chat_id, text):
    if not db.is_admin_chat(chat_id):
        await send_message(chat_id, "Admin only.")
        return
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await send_message(chat_id, "Usage: /broadcast <text>")
        return
    from .support import broadcast
    sent, failed = await broadcast(chat_id, parts[1].strip())
    await send_message(chat_id, f"Broadcast sent. Delivered: {sent}; failed: {failed}")


async def handle_users(chat_id):
    if not db.is_admin_chat(chat_id):
        await send_message(chat_id, "Admin only.")
        return
    keys = db.list_keys()
    await send_message(chat_id, "<b>Users</b>\n\n" + "\n".join(
        f"{html.escape(k.get('label') or 'unnamed')} — <code>{k['key_value']}</code>"
        for k in keys[:20]) if keys else "No users yet.")


async def handle_start(chat_id, text, user_name):
    key = db.get_key_by_telegram_chat_id(chat_id)
    if key:
        await send_message(chat_id, f"Welcome back, <b>{html.escape(user_name)}</b>. Type /help.")
    else:
        await send_message(chat_id, "Assist is invite-only. Ask the admin for an invite link.")


async def handle_help(chat_id, is_admin):
    text = ("<b>Assist commands</b>\n\n/status, /profile, /transcripts, "
            "/transcript &lt;id&gt;, /answers, /support, /unlink, /about")
    if is_admin:
        text += "\n\n<b>Admin</b>\n/inbox, /thread &lt;id&gt;, /reply &lt;id&gt; &lt;text&gt;, /broadcast &lt;text&gt;, /users"
    await send_message(chat_id, text)


async def handle_status(chat_id):
    key = db.get_key_by_telegram_chat_id(chat_id)
    if not key:
        await send_message(chat_id, "You're not linked to an account yet. Use /start.")
        return
    used = db.get_today_usage(key["key_id"])
    limit = db.get_key_daily_limit(key["key_id"], 200)
    status = "revoked" if key["revoked"] else ("active" if key["device_fingerprint"] else "not activated")
    await send_message(chat_id, f"<b>Account status</b>\n\nKey: <code>{html.escape(key['key_value'])}</code>\nStatus: {status}\nToday: {used} / {limit}")


async def handle_profile(chat_id):
    key = db.get_key_by_telegram_chat_id(chat_id)
    if not key:
        await send_message(chat_id, "Not linked. Use /start.")
        return
    profile = db.get_full_profile(key["key_id"]) or {}
    await send_message(chat_id, "<b>Your profile</b>\n\n" + "\n".join(
        f"<b>{html.escape(str(name))}:</b> {html.escape(str(value))}"
        for name, value in profile.items()))


async def handle_transcripts(chat_id):
    key = db.get_key_by_telegram_chat_id(chat_id)
    if not key:
        await send_message(chat_id, "Not linked. Use /start.")
        return
    transcripts = db.list_transcripts_for_key(key["key_id"], limit=10)
    await send_message(chat_id, "<b>Recent transcripts</b>\n\n" + "\n".join(
        f"<code>/transcript {t['transcript_id']}</code> {t.get('session_started', '')[:16]}"
        for t in transcripts) if transcripts else "No transcripts yet.")


async def handle_transcript_detail(chat_id, text):
    key = db.get_key_by_telegram_chat_id(chat_id)
    parts = text.split(maxsplit=1)
    transcript = db.get_transcript(parts[1].strip()) if len(parts) > 1 else None
    if not key or not transcript or transcript["key_id"] != key["key_id"]:
        await send_message(chat_id, "Transcript not found.")
        return
    await send_transcript(chat_id, transcript)


async def handle_answers(chat_id):
    key = db.get_key_by_telegram_chat_id(chat_id)
    answers = db.list_answers_for_key(key["key_id"], limit=10) if key else []
    await send_message(chat_id, "<b>Answer history</b>\n\n" + "\n".join(
        html.escape((answer.get("question") or "")[:80]) for answer in answers)
        if answers else "No saved answers yet.")


async def handle_support(chat_id):
    await send_message(chat_id, f"Send a message here to reach the admin. Email: {html.escape(SUPPORT_CONTACT)}")


async def handle_unlink(chat_id):
    with db._conn() as c:
        c.execute("UPDATE activation_keys SET telegram_chat_id = NULL WHERE telegram_chat_id = ?", (chat_id,))
    await send_message(chat_id, "Unlinked. Your key still works.")


async def handle_about(chat_id):
    await send_message(chat_id, "<b>Assist</b> listens to meeting audio, detects questions, and shows answers on a transparent desktop overlay.")