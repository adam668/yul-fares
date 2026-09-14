#!/usr/bin/env python3
"""Mail a warning when the daily run breaks. The workflow runs this on failure.

    python alert.py <run url>

Standard library only (config and mailer need nothing from pip), so it
still works when `pip install` or Python setup is the thing that broke.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

import config
import mailer

FALLBACK = ("The job failed before the fare scan could say why: a crash, a "
            "timeout, or a setup step (checkout, Python, pip install).")


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    problems_file = Path("run-problems.txt")
    problems = (problems_file.read_text(encoding="utf-8").splitlines()
                if problems_file.is_file() else [FALLBACK])

    subject = f"Fares from {config.ORIGIN}: today's run failed"
    items = "".join(f"<li style='margin:0 0 6px 0;'>{html.escape(p)}</li>" for p in problems)
    link = (f"<p><a href='{html.escape(url)}' style='color:#14213A;'>Open the run log</a></p>"
            if url else "")
    page = f"""<div style="font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;
        font-size:14px;line-height:20px;color:#14213A;max-width:560px;">
      <p><b>Today's fare run didn't finish cleanly.</b> Until it's fixed, a quiet
      inbox doesn't mean there were no deals.</p>
      <ul style="padding-left:18px;">{items}</ul>
      {link}
      <p style="color:#5C6B7A;font-size:12px;">Price history from the run was
      still saved. One bad day is usually Google being flaky; the same email
      two days running means something needs fixing.</p>
    </div>"""
    text = "\n".join(["Today's fare run didn't finish cleanly.", "", *problems, "", url])

    return 0 if mailer.send(subject, page, text) else 1


if __name__ == "__main__":
    sys.exit(main())
