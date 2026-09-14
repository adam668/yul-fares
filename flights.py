"""Talking to Google Flights.

Everything that knows about `fast_flights` is in this file. If the library
breaks — and it will, it rides on a private protobuf schema — this is the
only module you rewrite. Swap in SerpApi's google_flights engine or a
Travelpayouts month-matrix call behind the same three functions and
nothing downstream changes.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from fast_flights import (
    FlightQuery,
    Passengers,
    create_query,
    get_flights,
    get_return_flights,
    select_flight,
)

import config

log = logging.getLogger("flights")


class Blocked(Exception):
    """Google is refusing us. Stop the run rather than dig the hole deeper."""


@dataclass
class Leg:
    origin: str
    dest: str
    depart: str          # "2026-11-12 18:40"
    arrive: str
    minutes: int
    airline: str
    number: str
    aircraft: str


@dataclass
class Quote:
    dest: str
    depart_date: str
    return_date: str
    nights: int
    price: float
    airlines: list[str]
    stops: int
    outbound: list[Leg] = field(default_factory=list)
    inbound: list[Leg] = field(default_factory=list)
    url: str = ""

    @property
    def total_minutes(self) -> int:
        return sum(l.minutes for l in self.outbound)


# ---------------------------------------------------------------- helpers


def _sleep() -> None:
    time.sleep(random.uniform(*config.REQUEST_DELAY))


def _stamp(sdt) -> str:
    # Google drops trailing zeros: 16:00 arrives as [16], midnight as [].
    y, m, d = (list(sdt.date or []) + [0, 0, 0])[:3]
    hh, mm = (list(sdt.time or []) + [0, 0])[:2]
    return f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}"


def _legs(raw_flights) -> list[Leg]:
    return [
        Leg(
            origin=f.from_airport.code,
            dest=f.to_airport.code,
            depart=_stamp(f.departure),
            arrive=_stamp(f.arrival),
            minutes=f.duration or 0,
            airline=f.airline_code,
            number=f.flight_number,
            aircraft=f.plane_type or "",
        )
        for f in raw_flights
    ]


def _build_query(origin: str, dest: str, depart: str, ret: str):
    legs = [
        FlightQuery(date=depart, from_airport=origin, to_airport=dest,
                    max_stops=config.MAX_STOPS),
        FlightQuery(date=ret, from_airport=dest, to_airport=origin,
                    max_stops=config.MAX_STOPS),
    ]
    return create_query(
        flights=legs,
        trip="round-trip",
        seat=config.CABIN,
        passengers=Passengers(adults=1),
        currency=config.CURRENCY,
        language=config.LANGUAGE,
    )


# ---------------------------------------------------------------- one price


def price(origin: str, dest: str, depart: str, ret: str) -> Quote | None:
    """Cheapest round-trip for one exact pair of dates.

    Google prices a round-trip search by showing outbound options carrying
    the *total* trip price, so one request is enough for the number. The
    return legs need a second request, which `expand` does — only worth
    spending on fares that already cleared the bar.
    """
    q = _build_query(origin, dest, depart, ret)
    delay = config.RETRY_BACKOFF

    for attempt in range(1, config.MAX_RETRIES + 1):
        _sleep()
        try:
            result = get_flights(q)
        except Exception as exc:                       # network, parse, anything
            log.debug("%s %s→%s attempt %d: %s", depart, origin, dest, attempt, exc)
            if attempt < config.MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
            continue

        diag = getattr(result, "diagnostics", None)
        if diag is not None and diag.status == "blocked":
            raise Blocked(f"blocked after {diag.attempts} attempts")
        if not result:
            return None

        priced = [f for f in result if f.price and f.price > 0]
        if not priced:
            return None
        best = min(priced, key=lambda f: f.price)
        legs = _legs(best.flights)

        nights = (date.fromisoformat(ret) - date.fromisoformat(depart)).days
        return Quote(
            dest=dest,
            depart_date=depart,
            return_date=ret,
            nights=nights,
            price=float(best.price),
            airlines=list(best.airlines or []),
            stops=max(len(legs) - 1, 0),
            outbound=legs,
            url=q.url(),
        )

    log.warning("giving up on %s→%s %s", origin, dest, depart)
    return None


def expand(origin: str, dest: str, quote: Quote) -> Quote:
    """Fill in the return legs. Best-effort; a failure just leaves them empty."""
    try:
        q = _build_query(origin, dest, quote.depart_date, quote.return_date)
        _sleep()
        out = get_flights(q)
        if not out:
            return quote
        chosen = min((f for f in out if f.price), key=lambda f: f.price)
        _sleep()
        back = get_return_flights(select_flight(q, chosen))
        if back:
            cheapest_back = min((f for f in back if f.price), key=lambda f: f.price)
            quote.inbound = _legs(cheapest_back.flights)
    except Exception as exc:
        log.debug("could not expand %s: %s", dest, exc)
    return quote


# ---------------------------------------------------------------- passes


def _sample_dates(n: int) -> list[date]:
    """Spread n departure dates across the horizon, nudged off peak days.

    An even spread would land on the same weekday every time and miss
    whole categories of fare. The jitter fixes that.
    """
    start = date.today() + timedelta(days=config.SCAN_START_DAYS)
    span = config.SCAN_END_DAYS - config.SCAN_START_DAYS
    step = span / max(n - 1, 1)
    return [start + timedelta(days=int(i * step) + random.randint(-3, 3))
            for i in range(n)]


def scan(origin: str, dest: str) -> list[Quote]:
    """Cheap pass: is anything interesting happening on this route at all?

    A sparse sample across ten months. Real fare sales are published
    across wide date ranges, so eleven probes will land on one. Isolated
    single-date mistakes get missed — that's the trade for a run that
    finishes in fifteen minutes instead of eight hours.
    """
    quotes = []
    for d in _sample_dates(config.SCAN_SAMPLES):
        ret = d + timedelta(days=random.choice(config.TRIP_LENGTHS))
        q = price(origin, dest, d.isoformat(), ret.isoformat())
        if q:
            quotes.append(q)
    return quotes


def dive(origin: str, dest: str, around: str) -> list[Quote]:
    """Expensive pass: map the full date grid around a promising fare.

    Every departure date in the window crossed with every trip length.
    The grid is what lets the email say "this price, and here are the
    nine ways to spend it" instead of quoting one rigid itinerary.
    """
    centre = date.fromisoformat(around)
    earliest = date.today() + timedelta(days=7)
    quotes = []

    offsets = range(-config.DIVE_RADIUS_DAYS,
                    config.DIVE_RADIUS_DAYS + 1,
                    config.DIVE_STEP_DAYS)
    for off in offsets:
        depart = centre + timedelta(days=off)
        if depart < earliest:
            continue
        for nights in config.TRIP_LENGTHS:
            q = price(origin, dest, depart.isoformat(),
                      (depart + timedelta(days=nights)).isoformat())
            if q:
                quotes.append(q)
    return quotes
