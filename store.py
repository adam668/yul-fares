"""Price history. This is the whole reason the tool knows what 'cheap' means."""

from __future__ import annotations

import calendar
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS observation (
    id          INTEGER PRIMARY KEY,
    seen_on     TEXT NOT NULL,
    origin      TEXT NOT NULL,
    dest        TEXT NOT NULL,
    depart_date TEXT NOT NULL,
    return_date TEXT,
    price       REAL NOT NULL,
    currency    TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'scan'
);
CREATE INDEX IF NOT EXISTS obs_route_day ON observation (origin, dest, seen_on);

CREATE TABLE IF NOT EXISTS route_day (
    seen_on   TEXT NOT NULL,
    origin    TEXT NOT NULL,
    dest      TEXT NOT NULL,
    median    REAL NOT NULL,
    low       REAL NOT NULL,
    samples   INTEGER NOT NULL,
    PRIMARY KEY (seen_on, origin, dest)
);

CREATE TABLE IF NOT EXISTS route_low (
    origin   TEXT NOT NULL,
    dest     TEXT NOT NULL,
    price    REAL NOT NULL,
    seen_on  TEXT NOT NULL,
    PRIMARY KEY (origin, dest)
);

CREATE TABLE IF NOT EXISTS alerted (
    origin     TEXT NOT NULL,
    dest       TEXT NOT NULL,
    price      REAL NOT NULL,
    first_sent TEXT NOT NULL,
    last_sent  TEXT NOT NULL,
    PRIMARY KEY (origin, dest, price)
);
"""

# How far back a baseline looks. Observations older than this (plus a
# margin) are pruned; route_day and route_low keep the long view.
BASELINE_DAYS = 60
PRUNE_MARGIN_DAYS = 5
DIVE_KEEP_DAYS = 7          # dive rows only ever matter for today's email

# A seasonal baseline needs this many days of scans in its window before
# it's trusted over the whole-year one.
SEASON_MIN_DAYS = 5

# Scan size before `kind` existed, used only to untangle old rows.
LEGACY_SCAN_SAMPLES = 11


class Baseline(NamedTuple):
    price: float | None
    days: int
    season: str = ""        # "Nov–Jan" when seasonal, "" when whole-year


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()
        if not self.db.execute("SELECT 1 FROM route_low LIMIT 1").fetchone():
            # SQLite returns the seen_on of the MIN(price) row here.
            self.db.execute(
                "INSERT INTO route_low (origin, dest, price, seen_on) "
                "SELECT origin, dest, MIN(price), seen_on FROM observation GROUP BY origin, dest")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def _migrate(self) -> None:
        """Split dive rows out of databases written before `kind` existed.

        Back then a dive's grid was stored like a scan and replaced that
        day's route_day median with the grid's — a cluster of fares around
        a cheap date, which dragged the baseline down after every dive.
        Each route's scan rows went in as one unbroken run of ids and its
        dive rows much later, so everything after the first gap is a dive.
        """
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(observation)")}
        if "kind" in cols:
            return
        self.db.execute(
            "ALTER TABLE observation ADD COLUMN kind TEXT NOT NULL DEFAULT 'scan'")

        groups: dict[tuple, list[int]] = defaultdict(list)
        for r in self.db.execute(
                "SELECT id, seen_on, origin, dest FROM observation ORDER BY id"):
            groups[(r["seen_on"], r["origin"], r["dest"])].append(r["id"])

        for (seen_on, origin, dest), ids in groups.items():
            cut = next((i for i in range(1, len(ids)) if ids[i] != ids[i - 1] + 1),
                       len(ids))
            cut = min(cut, LEGACY_SCAN_SAMPLES)
            if cut == len(ids):
                continue
            self.db.executemany("UPDATE observation SET kind='dive' WHERE id=?",
                                [(i,) for i in ids[cut:]])
            prices = [r["price"] for r in self.db.execute(
                f"SELECT price FROM observation WHERE id IN ({','.join('?' * cut)})",
                ids[:cut])]
            self.db.execute(
                "INSERT OR REPLACE INTO route_day (seen_on, origin, dest, median, low, samples) "
                "VALUES (?,?,?,?,?,?)",
                (seen_on, origin, dest, statistics.median(prices), min(prices), len(prices)),
            )

    # ------------------------------------------------------------ writing

    def record_scan(self, origin, dest, currency, quotes, kind="scan", today=None):
        """quotes: list of (depart_date, return_date|None, price).

        Only kind="scan" feeds the baseline. Dive grids are stored for the
        record (and lowest_ever) but are clustered around a fare that was
        already cheap, so letting them into route_day would bias it down.
        """
        today = today or date.today().isoformat()
        if not quotes:
            return
        self.db.executemany(
            "INSERT INTO observation (seen_on, origin, dest, depart_date, "
            "return_date, price, currency, kind) VALUES (?,?,?,?,?,?,?,?)",
            [(today, origin, dest, d, r, p, currency, kind) for d, r, p in quotes],
        )
        prices = [p for _, _, p in quotes]
        self.db.execute(
            "INSERT INTO route_low (origin, dest, price, seen_on) VALUES (?,?,?,?) "
            "ON CONFLICT(origin, dest) DO UPDATE SET price=excluded.price, "
            "seen_on=excluded.seen_on WHERE excluded.price < route_low.price",
            (origin, dest, min(prices), today),
        )
        if kind == "scan":
            self.db.execute(
                "INSERT OR REPLACE INTO route_day (seen_on, origin, dest, median, low, samples) "
                "VALUES (?,?,?,?,?,?)",
                (today, origin, dest, statistics.median(prices), min(prices), len(prices)),
            )
        self.db.commit()

    # ------------------------------------------------------------ reading

    def baseline(self, origin: str, dest: str, around: str | None = None,
                 lookback_days: int = BASELINE_DAYS) -> Baseline:
        """What this route normally costs — for departures near `around`.

        The median of each day's median. Taking the median twice is the
        point: one anomalous sampled date can't drag it down, and neither
        can one anomalous day of scanning.

        With `around`, only departures within a month either side count, so
        a July fare to Huatulco is measured against July-ish fares rather
        than a year that includes the winter-sun peak. Until that window has
        SEASON_MIN_DAYS days of scans it falls back to the whole-year
        baseline, which on a fresh database is today's own scan.
        """
        since = (date.today() - timedelta(days=lookback_days)).isoformat()

        if around:
            m = int(around[5:7])
            months = [(m + k - 1) % 12 + 1 for k in (-1, 0, 1)]
            rows = self.db.execute(
                "SELECT seen_on, price FROM observation "
                "WHERE origin=? AND dest=? AND kind='scan' AND seen_on>=? "
                "AND CAST(substr(depart_date, 6, 2) AS INTEGER) IN (?,?,?)",
                (origin, dest, since, *months),
            ).fetchall()
            by_day: dict[str, list[float]] = defaultdict(list)
            for r in rows:
                by_day[r["seen_on"]].append(r["price"])
            if len(by_day) >= SEASON_MIN_DAYS:
                medians = [statistics.median(p) for p in by_day.values()]
                label = f"{calendar.month_abbr[months[0]]}–{calendar.month_abbr[months[2]]}"
                return Baseline(statistics.median(medians), len(medians), label)

        rows = self.db.execute(
            "SELECT median FROM route_day WHERE origin=? AND dest=? AND seen_on>=?",
            (origin, dest, since),
        ).fetchall()
        if not rows:
            return Baseline(None, 0)
        medians = [r["median"] for r in rows]
        return Baseline(statistics.median(medians), len(medians))

    def lowest_ever(self, origin: str, dest: str):
        """Cheapest fare ever seen on the route, dives included: (price, seen_on).

        Kept in its own table because observations are pruned.
        """
        row = self.db.execute(
            "SELECT price, seen_on FROM route_low WHERE origin=? AND dest=?",
            (origin, dest),
        ).fetchone()
        return (row["price"], row["seen_on"]) if row else (None, None)

    def daily_lows(self, origin: str, dest: str, days: int = 90):
        since = (date.today() - timedelta(days=days)).isoformat()
        rows = self.db.execute(
            "SELECT seen_on, low FROM route_day WHERE origin=? AND dest=? "
            "AND seen_on>=? ORDER BY seen_on",
            (origin, dest, since),
        ).fetchall()
        return [(r["seen_on"], r["low"]) for r in rows]

    # ------------------------------------------------------------ upkeep

    def prune(self, today: date | None = None) -> None:
        """Drop rows no baseline will read again, so prices.db stays small.

        Unpruned, a year of 100 routes a day is ~60 MB. Baselines read 60
        days of scans; dive rows are dead once the day's email is out;
        route_day (one row per route per scan) and route_low keep the long
        view for a few MB a decade.
        """
        today = today or date.today()
        scans = (today - timedelta(days=BASELINE_DAYS + PRUNE_MARGIN_DAYS)).isoformat()
        dives = (today - timedelta(days=DIVE_KEEP_DAYS)).isoformat()
        self.db.execute("DELETE FROM observation WHERE seen_on < ?", (scans,))
        self.db.execute("DELETE FROM observation WHERE kind='dive' AND seen_on < ?", (dives,))
        self.db.execute("DELETE FROM alerted WHERE last_sent < ?", (scans,))
        self.db.commit()
        self.db.execute("VACUUM")

    # ------------------------------------------------------------ dedupe

    def already_alerted(self, origin: str, dest: str, price: float,
                        within_days: int = 10, tolerance: float = 0.03) -> bool:
        """True if we mailed about this route at roughly this price recently.

        Fares wobble by a few dollars day to day. Without the tolerance
        band you get the same deal re-sent every morning at $612, $608,
        $612 until it expires.
        """
        since = (date.today() - timedelta(days=within_days)).isoformat()
        rows = self.db.execute(
            "SELECT price FROM alerted WHERE origin=? AND dest=? AND last_sent>=?",
            (origin, dest, since),
        ).fetchall()
        return any(abs(r["price"] - price) <= price * tolerance for r in rows)

    def mark_alerted(self, origin: str, dest: str, price: float) -> None:
        today = date.today().isoformat()
        self.db.execute(
            "INSERT INTO alerted (origin, dest, price, first_sent, last_sent) "
            "VALUES (?,?,?,?,?) ON CONFLICT(origin, dest, price) "
            "DO UPDATE SET last_sent=excluded.last_sent",
            (origin, dest, price, today, today),
        )
        self.db.commit()
