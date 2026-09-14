"""Sending. Resend's REST API over stdlib — no extra dependency for one POST."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

import config

log = logging.getLogger("mail")

ENDPOINT = "https://api.resend.com/emails"


def send(subject: str, html: str, text: str) -> bool:
    if not config.RESEND_API_KEY or not config.MAIL_TO:
        log.warning("RESEND_API_KEY or MAIL_TO missing — not sending")
        return False

    payload = json.dumps({
        "from": config.MAIL_FROM,
        "to": [a.strip() for a in config.MAIL_TO.split(",") if a.strip()],
        "subject": subject,
        "html": html,
        "text": text,
    }).encode()

    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Content-Type": "application/json",
            # Cloudflare in front of Resend rejects urllib's default
            # "Python-urllib/3.x" agent with a bare 403 (error 1010).
            "User-Agent": "yul-fares/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            log.info("sent (%s)", resp.status)
            return True
    except urllib.error.HTTPError as exc:
        log.error("resend rejected it: %s %s", exc.code, exc.read().decode()[:400])
    except Exception as exc:
        log.error("could not send: %s", exc)
    return False
