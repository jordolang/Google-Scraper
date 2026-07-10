"""
salescall — interactive sales-call cockpit for Jlang.dev outreach.

Turns scraped business data into a prioritized call queue, deep per-business
website intelligence, and a real-time teleprompter that arms a caller with
personalized dialogue, objection handling, and selling points.
"""

__version__ = "0.1.0"


def _load_env() -> None:
    """Load secrets from a local .env (PAGESPEED_API_KEY, SMTP creds).

    Never raises — if python-dotenv is absent or no .env exists, real
    environment variables still work as-is.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


_load_env()
