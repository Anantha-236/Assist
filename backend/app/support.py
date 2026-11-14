"""Two-way support messaging between users and admins via Telegram."""

import html

from . import db
from .telegram_service import send_message


async def relay_user_message(user_chat_id: str, text: str) -> bool:
    admins = db.list_admin_chats()
    thread_id = db.get_or_create_thread(user_chat_id)
    to_chat_id = admins[0]["chat_id"] if admins else "unrouted"
    key = db.get_key_by_telegram_chat_id(user_chat_id)
    db.insert_support_message(
        thread_id, user_chat_id, to_chat_id, "user_to_admin", text,
        key["key_id"] if key else None)
    if not admins:
        await send_message(user_chat_id,
                           "No admin is registered yet. Your message was saved.")
        return False

    label = (key and key.get("label")) or f"chat {user_chat_id}"
    preview = (f"<b>Support message</b>\n<b>From:</b> {html.escape(label)}\n"
               f"<b>Chat:</b> <code>{html.escape(user_chat_id)}</code>\n\n"
               f"{html.escape(text[:600])}")
    if len(text) > 600:
        preview += "\n<i>Truncated. See the web dashboard for the full message.</i>"
    preview += (f"\n\n<i>Reply with:</i> <code>/reply {thread_id} &lt;message&gt;</code>")
    for admin in admins:
        await send_message(admin["chat_id"], preview)
    await send_message(user_chat_id,
                       "Your message has been sent to the admin.")
    return True


async def admin_reply_to_thread(admin_chat_id: str, thread_id: str, text: str):
    if not db.is_admin_chat(admin_chat_id):
        return False, "You are not registered as admin. Use /register_admin first."
    messages = db.list_thread_messages(thread_id)
    if not messages:
        return False, f"No thread found with id {thread_id}"
    user_chat_id = messages[0]["from_chat_id"]
    db.insert_support_message(thread_id, admin_chat_id, user_chat_id,
                              "admin_to_user", text)
    return await send_message(
        user_chat_id,
        f"<b>Message from Assist support</b>\n\n{html.escape(text)}")


async def broadcast(admin_chat_id: str, text: str) -> tuple[int, int]:
    if not db.is_admin_chat(admin_chat_id):
        return 0, 0
    sent = failed = 0
    for chat_id in db.list_all_user_chat_ids():
        ok, _ = await send_message(
            chat_id, f"<b>Announcement from Assist</b>\n\n{html.escape(text)}")
        sent += int(ok)
        failed += int(not ok)
    return sent, failed


def format_thread_for_admin(thread_id: str) -> str:
    messages = db.list_thread_messages(thread_id)
    if not messages:
        return f"No messages in thread {thread_id}."
    lines = [f"<b>Conversation {html.escape(thread_id[:10])}</b>\n"]
    for message in messages[-20:]:
        who = "User" if message["direction"] == "user_to_admin" else "Admin"
        lines.append(f"<b>{who}</b> <code>{message['created_at'][11:16]}</code>\n"
                     f"{html.escape(message['text'][:300])}")
    return "\n\n".join(lines)