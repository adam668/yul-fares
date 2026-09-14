#!/usr/bin/env python3
"""Daily run: scan every route, dive on the promising ones, mail what clears the bar.

    python run.py                 # full run, sends email
    python run.py --dry           # full run, writes preview.html, sends nothing
    python run.py --only LIS,NRT  # restrict to a few routes while testing
    python run.py --all           # ignore SCAN_EVERY_DAYS, scan every route today
    python run.py --preview       # render sample data, no network at all
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import config
import deals as D
import flights
import mailer
import render
from store import Store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run")

# A Windows console can't encode every city name; don't crash on printing one.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def due_today(code: str, today: date | None = None) -> bool:
    """Spread the route list across SCAN_EVERY_DAYS days.

    Keyed on the IATA code rather than list position, so adding or
    removing a destination doesn't move every other route to a new day.
    """
    n = max(config.SCAN_EVERY_DAYS, 1)
    today = today or date.today()
    return sum(map(ord, code)) % n == today.toordinal() % n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="no email, write preview.html")
    ap.add_argument("--only", default="", help="comma-separated IATA codes")
    ap.add_argument("--all", action="store_true", help="scan every route, not today's share")
    ap.add_argument("--preview", action="store_true", help="render fake data and stop")
    args = ap.parse_args()

    if args.preview:
        from sample import sample_deals
        page = render.html(sample_deals(), scanned=len(config.DESTINATIONS),
                           started=datetime.now())
        Path("preview.html").write_text(page, encoding="utf-8")
        log.info("wrote preview.html")
        return 0

    started = datetime.now()
    store = Store(config.DB_PATH)
    origin = config.ORIGIN

    targets = config.DESTINATIONS
    if args.only:
        wanted = {c.strip().upper() for c in args.only.split(",")}
        targets = [d for d in targets if d[0] in wanted]
    elif not args.all:
        targets = [d for d in targets if due_today(d[0])]
    log.info("scanning %d of %d routes", len(targets), len(config.DESTINATIONS))

    # ---------------------------------------------------------- pass one
    candidates = []
    for code, city, region in targets:
        try:
            quotes = flights.scan(origin, code)
        except flights.Blocked:
            log.error("Google is blocking us — stopping the run early")
            break
        except Exception as exc:
            log.warning("scan failed for %s: %s", code, exc)
            continue

        if not quotes:
            log.info("%-4s no fares returned", code)
            continue

        store.record_scan(origin, code, config.CURRENCY,
                          [(q.depart_date, q.return_date, q.price) for q in quotes])

        baseline, days = store.baseline(origin, code)
        baseline = baseline or D.scan_baseline(quotes)
        hit = D.candidate(quotes, baseline)

        log.info("%-4s low %6.0f  baseline %6.0f  (%d days)%s",
                 code, min(q.price for q in quotes), baseline or 0, days,
                 "  <- candidate" if hit else "")

        if hit:
            candidates.append((code, city, region, hit, baseline, days))

    # Dive on the deepest discounts first; the budget is the scarce thing.
    candidates.sort(key=lambda c: c[3].price / c[4])
    candidates = candidates[:config.MAX_DEEP_DIVES]

    # ---------------------------------------------------------- pass two
    found = []
    for code, city, region, hit, baseline, days in candidates:
        log.info("diving on %s around %s", code, hit.depart_date)
        try:
            grid = flights.dive(origin, code, hit.depart_date)
        except flights.Blocked:
            log.error("blocked mid-dive — mailing what we have")
            break
        except Exception as exc:
            log.warning("dive failed for %s: %s", code, exc)
            continue

        if not grid:
            continue

        store.record_scan(origin, code, config.CURRENCY,
                          [(q.depart_date, q.return_date, q.price) for q in grid])

        deal = D.build(code, city, region, grid, baseline, days)
        if not deal:
            log.info("%s didn't clear the bar on the full grid", code)
            continue

        if store.already_alerted(origin, code, deal.price):
            log.info("%s already mailed at ~%.0f", code, deal.price)
            continue

        low, _ = store.lowest_ever(origin, code)
        deal.lowest_ever = low
        deal.is_record = low is not None and deal.price <= low
        deal.best = flights.expand(origin, code, deal.best)
        found.append(deal)

    found = D.rank(found)

    # ---------------------------------------------------------- deliver
    page = render.html(found, scanned=len(targets), started=started)
    plain = render.text(found, scanned=len(targets))
    subject = render.subject(found)

    log.info("%d deal(s) in %s", len(found), datetime.now() - started)
    print(plain)

    if args.dry:
        Path("preview.html").write_text(page, encoding="utf-8")
        log.info("dry run — preview.html written, nothing sent")
    elif found or config.SEND_WHEN_EMPTY:
        if mailer.send(subject, page, plain):
            for d in found:
                store.mark_alerted(origin, d.dest, d.price)
    else:
        log.info("nothing cleared the bar, staying quiet")

    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
