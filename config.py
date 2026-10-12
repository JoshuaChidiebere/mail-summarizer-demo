import os

# Loads local .env for dev convenience if python-dotenv is installed and a
# .env file exists. On Render/HF Spaces/etc., real env vars set in the
# platform dashboard take precedence — this is just for running locally.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    MAIL_EMAIL = os.environ.get("MAIL_EMAIL")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")

    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_IDS = [
        c.strip() for c in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()
    ]

    SENDER_FILTER = os.environ.get("SENDER_FILTER", "").strip()
    DAYS_BACK = int(os.environ.get("DAYS_BACK", "0"))

    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")


    @classmethod
    def validate(cls):
        missing = [
            name for name, val in [
                ("MAIL_EMAIL", cls.MAIL_EMAIL),
                ("MAIL_PASSWORD", cls.MAIL_PASSWORD),
                ("TELEGRAM_BOT_TOKEN", cls.TELEGRAM_BOT_TOKEN),
            ] if not val
        ]
        if not cls.TELEGRAM_CHAT_IDS:
            missing.append("TELEGRAM_CHAT_IDS")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Set them in your platform's dashboard (or a local .env for testing)."
            )
