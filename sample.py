"""Fake deals for `python run.py --preview`.

Lets you iterate on the email in a browser without waiting twenty minutes
for a real run, and gives you something to look at on day one.
"""

from __future__ import annotations

from datetime import date, timedelta

from deals import Deal, Option, Tier
from flights import Leg, Quote


def _opt(depart: date, nights: int, price: float, airlines, stops):
    ret = depart + timedelta(days=nights)
    return Option(
        depart_date=depart.isoformat(),
        return_date=ret.isoformat(),
        nights=nights,
        price=price,
        airlines=airlines,
        stops=stops,
        url=("https://www.google.com/travel/flights?q=Flights%20to%20LIS%20from%20YUL"
             f"%20on%20{depart.isoformat()}%20through%20{ret.isoformat()}"),
    )


def sample_deals() -> list[Deal]:
    base = date.today() + timedelta(days=64)

    tier_a = Tier(price=412, options=[
        _opt(base + timedelta(days=d), n, 412, ["TAP Air Portugal"], 0)
        for d, n in [(0, 7), (0, 9), (2, 7), (2, 11), (4, 9), (4, 14),
                     (6, 7), (8, 11), (10, 9), (12, 14), (14, 7)]
    ])
    tier_b = Tier(price=438, options=[
        _opt(base + timedelta(days=d), n, 438, ["TAP Air Portugal"], 0)
        for d, n in [(16, 7), (18, 9), (20, 14), (22, 11)]
    ])

    lisbon = Deal(
        dest="LIS", city="Lisbon", region="Europe",
        price=412, baseline=742, history_days=41,
        tiers=[tier_a, tier_b],
        best=Quote(
            dest="LIS",
            depart_date=base.isoformat(),
            return_date=(base + timedelta(days=9)).isoformat(),
            nights=9, price=412, airlines=["TAP Air Portugal"], stops=0,
            outbound=[Leg("YUL", "LIS", f"{base} 20:55", f"{base} 08:20",
                          375, "TP", "256", "Airbus A330neo")],
            inbound=[Leg("LIS", "YUL", "— 13:40", "— 16:05",
                         445, "TP", "255", "Airbus A330neo")],
        ),
        lowest_ever=412, is_record=True,
    )

    tokyo_tier = Tier(price=876, options=[
        _opt(base + timedelta(days=d), n, 876, ["Air Canada", "ANA"], 1)
        for d, n in [(20, 11), (22, 14), (24, 11), (26, 17), (28, 14), (30, 21)]
    ])
    tokyo = Deal(
        dest="NRT", city="Tokyo", region="Asia",
        price=876, baseline=1580, history_days=41,
        tiers=[tokyo_tier],
        best=Quote(
            dest="NRT",
            depart_date=(base + timedelta(days=20)).isoformat(),
            return_date=(base + timedelta(days=31)).isoformat(),
            nights=11, price=876, airlines=["Air Canada", "ANA"], stops=1,
            outbound=[
                Leg("YUL", "YVR", "— 08:10", "— 10:35", 325, "AC", "301", "Boeing 787-9"),
                Leg("YVR", "NRT", "— 13:25", "— 15:50", 605, "NH", "117", "Boeing 787-9"),
            ],
        ),
    )
    return [tokyo, lisbon]
