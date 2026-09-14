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
from collections import Counter
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


PROBLEMS_FILE = Path("run-problems.txt")


def health(stats: Counter, attempted: int) -> list[str]:
    """Reasons this run shouldn't count as a success.

    A broken scraper looks exactly like a quiet day for fares — no deals,
    no email — so anything that smells like breakage fails the job
    instead, and the workflow mails about it.
    """
    problems = []
    if stats["blocked"]:
        problems.append("Google blocked the run, so it stopped early.")
    if attempted and stats["scan_failed"] > attempted * 0.10:
        problems.append(f"{stats['scan_failed']} of {attempted} route scans raised errors "
                        "(Google may have changed its format; try bumping faster-flights).")
    if attempted and stats["empty"] > attempted * 0.5:
        problems.append(f"{stats['empty']} of {attempted} routes returned no fares at all.")
    if stats["dives"] and stats["dive_failed"] > stats["dives"] * 0.5:
        problems.append(f"{stats['dive_failed']} of {stats['dives']} deep dives raised errors.")
    if stats["mail_failed"]:
        problems.append("The deals email couldn't be sent (check the Resend key and domain).")
    return problems


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
    stats: Counter = Counter()
    candidates = []
    for code, city, region in targets:
        try:
            quotes = flights.scan(origin, code)
        except flights.Blocked:
            log.error("Google is blocking us — stopping the run early")
            stats["blocked"] += 1
            break
        except Exception as exc:
            log.warning("scan failed for %s: %s", code, exc)
            stats["scan_failed"] += 1
            continue

        if not quotes:
            log.info("%-4s no fares returned", code)
            stats["empty"] += 1
            continue

        store.record_scan(origin, code, config.CURRENCY,
                          [(q.depart_date, q.return_date, q.price) for q in quotes])

        refs = {q.depart_date: store.baseline(origin, code, around=q.depart_date)
                for q in quotes}
        hit = D.candidate(quotes, lambda q: refs[q.depart_date].price)

        cheapest = min(quotes, key=lambda q: q.price)
        shown_quote, shown_ref = hit or (cheapest, refs[cheapest.depart_date].price)
        ref = refs[shown_quote.depart_date]
        log.info("%-4s %s %6.0f  baseline %6.0f  (%d days%s)%s",
                 code, "hit" if hit else "low", shown_quote.price, shown_ref or 0,
                 ref.days, f", {ref.season}" if ref.season else "",
                 "  <- candidate" if hit else "")

        if hit:
            quote, baseline = hit
            candidates.append((code, city, region, quote, baseline, ref.days, ref.season))

    # Dive on the deepest discounts first; the budget is the scarce thing.
    candidates.sort(key=lambda c: c[3].price / c[4])
    candidates = candidates[:config.MAX_DEEP_DIVES]

    # ---------------------------------------------------------- pass two
    found = []
    for code, city, region, hit, baseline, days, season in candidates:
        log.info("diving on %s around %s", code, hit.depart_date)
        stats["dives"] += 1
        try:
            grid = flights.dive(origin, code, hit.depart_date)
        except flights.Blocked:
            log.error("blocked mid-dive — mailing what we have")
            stats["blocked"] += 1
            break
        except Exception as exc:
            log.warning("dive failed for %s: %s", code, exc)
            stats["dive_failed"] += 1
            continue

        if not grid:
            continue

        store.record_scan(origin, code, config.CURRENCY,
                          [(q.depart_date, q.return_date, q.price) for q in grid],
                          kind="dive")

        deal = D.build(code, city, region, grid, baseline, days, season)
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
            stats["mail_failed"] += 1
    else:
        log.info("nothing cleared the bar, staying quiet")

    store.prune()
    store.close()

    problems = health(stats, len(targets))
    PROBLEMS_FILE.unlink(missing_ok=True)
    if problems:
        for p in problems:
            log.error("unhealthy run: %s", p)
        PROBLEMS_FILE.write_text("\n".join(problems), encoding="utf-8")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
