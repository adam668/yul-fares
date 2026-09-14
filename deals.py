"""Deciding what counts as a deal, and shaping it for the email."""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import config
from flights import Quote


@dataclass
class Option:
    """One bookable way to fly the deal."""
    depart_date: str
    return_date: str
    nights: int
    price: float
    airlines: list[str]
    stops: int
    url: str

    @property
    def weekday_pair(self) -> str:
        d = date.fromisoformat(self.depart_date).strftime("%a")
        r = date.fromisoformat(self.return_date).strftime("%a")
        return f"{d}–{r}"


@dataclass
class Tier:
    """A price, and every date combination that buys it."""
    price: float
    options: list[Option] = field(default_factory=list)

    @property
    def nights_range(self) -> tuple[int, int]:
        n = [o.nights for o in self.options]
        return min(n), max(n)

    @property
    def date_span(self) -> tuple[str, str]:
        d = sorted(o.depart_date for o in self.options)
        return d[0], d[-1]


@dataclass
class Deal:
    dest: str
    city: str
    region: str
    price: float
    baseline: float
    history_days: int
    tiers: list[Tier]
    best: Quote
    lowest_ever: float | None = None
    is_record: bool = False
    sparkline: list[tuple[str, float]] = field(default_factory=list)

    @property
    def discount(self) -> float:
        return 1 - (self.price / self.baseline)

    @property
    def saving(self) -> float:
        return self.baseline - self.price

    @property
    def option_count(self) -> int:
        return sum(len(t.options) for t in self.tiers)


# ---------------------------------------------------------------- scanning


def candidate(quotes: list[Quote], baseline: float | None) -> Quote | None:
    """Does this route deserve the expensive deep dive?

    Deliberately looser than the real bar. The scan samples eleven dates
    out of three hundred, so the cheapest date it happened to hit is
    usually a little above the true floor for that sale. Screening at the
    full 40% here would throw away routes the dive would have qualified.
    """
    if not quotes:
        return None
    ref = baseline or statistics.median(q.price for q in quotes)
    cheapest = min(quotes, key=lambda q: q.price)

    screen = config.DISCOUNT_FLOOR * 0.7
    if cheapest.price > ref * (1 - screen):
        return None
    if cheapest.price > config.MAX_PRICE:
        return None
    return cheapest


def scan_baseline(quotes: list[Quote]) -> float | None:
    return statistics.median(q.price for q in quotes) if quotes else None


# ---------------------------------------------------------------- shaping


def _tiers(quotes: list[Quote], *, spread: float = 0.08, limit: int = 4) -> list[Tier]:
    """Group the grid by price.

    Identical fares across different trip lengths are not a coincidence —
    it's the same fare bucket on the same flights, and the return date
    genuinely doesn't change the price. Surfacing that is the whole point:
    you pick the length that suits you, not the one the fare forces.

    Prices within `spread` of the cheapest are kept, so a fare that's $30
    more but opens up two extra weeks of dates still shows up.
    """
    if not quotes:
        return []

    buckets: dict[float, list[Quote]] = defaultdict(list)
    for q in quotes:
        buckets[round(q.price)].append(q)

    floor = min(buckets)
    kept = sorted(p for p in buckets if p <= floor * (1 + spread))[:limit]

    out = []
    for p in kept:
        options = [
            Option(
                depart_date=q.depart_date,
                return_date=q.return_date,
                nights=q.nights,
                price=q.price,
                airlines=q.airlines,
                stops=q.stops,
                url=q.url,
            )
            for q in sorted(buckets[p], key=lambda q: (q.depart_date, q.nights))
        ]
        out.append(Tier(price=float(p), options=options))
    return out


def build(dest: str, city: str, region: str, quotes: list[Quote],
          baseline: float, history_days: int) -> Deal | None:
    """Apply the real bar and assemble the deal, or return nothing."""
    if not quotes:
        return None

    tiers = _tiers(quotes)
    if not tiers:
        return None

    price = tiers[0].price
    if price > config.MAX_PRICE:
        return None
    if price > baseline * (1 - config.DISCOUNT_FLOOR):
        return None
    if baseline - price < config.MIN_ABS_SAVING:
        return None

    cheapest = min(quotes, key=lambda q: (q.price, q.total_minutes))
    return Deal(
        dest=dest, city=city, region=region,
        price=price, baseline=baseline, history_days=history_days,
        tiers=tiers, best=cheapest,
    )


def rank(deals: list[Deal]) -> list[Deal]:
    """Biggest discount first, absolute saving breaking ties."""
    return sorted(deals, key=lambda d: (-d.discount, -d.saving))
