import time
import re
from datetime import date, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread

import ollama
import requests
from bs4 import BeautifulSoup
from imap_tools import MailBox, AND

from config import Config


# ========================= PLATFORM HEALTH CHECK =========================
def run_health_server():
    """Keeps Render/HF Spaces happy by listening for basic web requests."""
    server = HTTPServer(("0.0.0.0", Config.PORT), SimpleHTTPRequestHandler)
    server.serve_forever()


# ========================= EMAIL HANDLING =========================
def clean_email_body(msg) -> str:
    """Prefer plain text; fall back to stripped HTML."""
    if msg.text and len(msg.text.strip()) > 20:
        return msg.text.strip()

    if msg.html:
        soup = BeautifulSoup(msg.html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()

    return ""


def summarize_email(body: str, model: str = None) -> str:
    """Summarize email using local Ollama."""
    model = model or Config.OLLAMA_MODEL

    if not body or len(body) < 30:
        return "Email body is too short or empty."

    prompt = f"""You are an expert assistant. Summarize the following email clearly and concisely.

Focus on:
- Main purpose
- Key points
- Any deadlines or important dates
- Required actions

EMAIL:
{body}

SUMMARY:"""

    try:
        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        return response["message"]["content"].strip()
    except Exception as e:
        return f"[Summarization failed: {str(e)}]"


def send_telegram_summary(subject: str, sender: str, summary_text: str) -> bool:
    """Sends the summary to every configured chat. Returns True only if
    ALL sends succeeded — used to decide whether it's safe to mark the
    email as read (so a Telegram outage doesn't silently swallow mail)."""
    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"

    message_text = (
        f"📧 *Email Reminder/Update*\n\n"
        f"👤 *From:* {sender}\n"
        f"📋 *Subject:* {subject}\n\n"
        f"*Summary:*\n{summary_text}"
    )

    all_ok = True
    for chat_id in Config.TELEGRAM_CHAT_IDS:
        payload = {"chat_id": chat_id, "text": message_text, "parse_mode": "Markdown"}
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 400:
                # Markdown formatting was rejected; retry as plain text
                payload.pop("parse_mode")
                response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                print(f"🚀 Summary sent to chat {chat_id}")
            else:
                all_ok = False
                print(f"❌ Telegram API error for chat {chat_id}: {response.text}")
        except Exception as e:
            all_ok = False
            print(f"❌ Failed to reach Telegram for chat {chat_id}: {e}")

    return all_ok


def process_emails():
    print("🔄 Connecting to mailbox...")

    try:
        with MailBox(Config.IMAP_SERVER).login(
            Config.MAIL_EMAIL, Config.MAIL_PASSWORD, initial_folder="INBOX"
        ) as mailbox:
            cutoff_date = date.today() - timedelta(days=Config.DAYS_BACK)

            criteria_kwargs = {"seen": False, "date_gte": cutoff_date}
            if Config.SENDER_FILTER:
                criteria_kwargs["from_"] = Config.SENDER_FILTER

            print(f"📨 Fetching unread emails since {cutoff_date}"
                  f"{f' from senders matching {Config.SENDER_FILTER!r}' if Config.SENDER_FILTER else ''}...")

            messages = mailbox.fetch(
                criteria=AND(**criteria_kwargs),
                mark_seen=False,  # we mark manually below, only after a successful send
                bulk=True,
                reverse=True,
            )

            email_count = 0

            for msg in messages:
                email_count += 1
                body = clean_email_body(msg)
                summary = summarize_email(body)

                print(f"{'=' * 90}")
                print(f"📧 Email {email_count}")
                print(f"Date    : {msg.date}")
                print(f"From    : {msg.from_}")
                print(f"Subject : {msg.subject}")
                print(f"{'-' * 60}")
                print(f"Summary :\n{summary}")
                print(f"{'=' * 90}\n")

                sent_ok = send_telegram_summary(msg.subject, msg.from_, summary)

                # Only mark as read once we've actually delivered the summary —
                # otherwise a Telegram hiccup means you'd never see it, since
                # the next run would skip it as already-read.
                if sent_ok:
                    mailbox.flag([msg.uid], ["\\Seen"], True)
                else:
                    print(f"⚠️  Leaving email {msg.uid} unread — will retry next run.")

            if email_count == 0:
                print("✅ No unread emails found in the selected period.")
            else:
                print(f"✅ Processed {email_count} unread email(s).")

    except Exception as e:
        print(f"❌ Error during check: {e}")


# ========================= EXECUTION LOOP =========================
if __name__ == "__main__":
    Config.validate()
    process_emails()