"""Price history. This is the whole reason the tool knows what 'cheap' means."""

from __future__ import annotations

import sqlite3
import statistics
from datetime import date, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS observation (
    id          INTEGER PRIMARY KEY,
    seen_on     TEXT NOT NULL,
    origin      TEXT NOT NULL,
    dest        TEXT NOT NULL,
    depart_date TEXT NOT NULL,
    return_date TEXT,
    price       REAL NOT NULL,
    currency    TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS alerted (
    origin     TEXT NOT NULL,
    dest       TEXT NOT NULL,
    price      REAL NOT NULL,
    first_sent TEXT NOT NULL,
    last_sent  TEXT NOT NULL,
    PRIMARY KEY (origin, dest, price)
);
"""


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------ writing

    def record_scan(self, origin, dest, currency, quotes, today=None):
        """quotes: list of (depart_date, return_date|None, price)."""
        today = today or date.today().isoformat()
        if not quotes:
            return
        self.db.executemany(
            "INSERT INTO observation (seen_on, origin, dest, depart_date, "
            "return_date, price, currency) VALUES (?,?,?,?,?,?,?)",
            [(today, origin, dest, d, r, p, currency) for d, r, p in quotes],
        )
        prices = [p for _, _, p in quotes]
        self.db.execute(
            "INSERT OR REPLACE INTO route_day (seen_on, origin, dest, median, low, samples) "
            "VALUES (?,?,?,?,?,?)",
            (today, origin, dest, statistics.median(prices), min(prices), len(prices)),
        )
        self.db.commit()

    # ------------------------------------------------------------ reading

    def baseline(self, origin: str, dest: str, lookback_days: int = 60):
        """What this route normally costs.

        The median of each day's median. Taking the median twice is the
        point: one anomalous sampled date can't drag it down, and neither
        can one anomalous day of scanning.

        Returns (baseline_price, days_of_history). On a fresh database
        this reads back today's own scan, which is a weak but usable
        reference — it firms up after about two weeks of runs.
        """
        since = (date.today() - timedelta(days=lookback_days)).isoformat()
        rows = self.db.execute(
            "SELECT median FROM route_day WHERE origin=? AND dest=? AND seen_on>=?",
            (origin, dest, since),
        ).fetchall()
        if not rows:
            return None, 0
        medians = [r["median"] for r in rows]
        return statistics.median(medians), len(medians)

    def lowest_ever(self, origin: str, dest: str):
        row = self.db.execute(
            "SELECT MIN(low) AS m, COUNT(*) AS n FROM route_day WHERE origin=? AND dest=?",
            (origin, dest),
        ).fetchone()
        return (row["m"], row["n"]) if row and row["m"] is not None else (None, 0)

    def daily_lows(self, origin: str, dest: str, days: int = 90):
        since = (date.today() - timedelta(days=days)).isoformat()
        rows = self.db.execute(
            "SELECT seen_on, low FROM route_day WHERE origin=? AND dest=? "
            "AND seen_on>=? ORDER BY seen_on",
            (origin, dest, since),
        ).fetchall()
        return [(r["seen_on"], r["low"]) for r in rows]

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
