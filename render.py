"""The email.

Built as a printed airline timetable rather than a newsletter, because the
content genuinely is one: a destination, a fare, and every departure that
sells at it. Inline styles and tables throughout — Gmail and Outlook drop
stylesheets, flexbox and grid.
"""

from __future__ import annotations

from datetime import date, datetime

import config
from deals import Deal

INK = "#14213A"
PAPER = "#FCFBF8"
AMBER = "#E09B2D"
SLATE = "#5C6B7A"
RULE = "#D8D3C8"
WASH = "#F3F0E9"

SERIF = "Georgia, 'Iowan Old Style', 'Times New Roman', serif"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"


def _money(v: float) -> str:
    return f"${v:,.0f}"


def _pretty(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%a %d %b").replace(" 0", " ")


def _hm(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


def _airlines(names: list[str]) -> str:
    return ", ".join(names) if names else "mixed carriers"


# ---------------------------------------------------------------- pieces


def _board(deal: Deal) -> str:
    """Ink panel, amber type. The one loud element per deal."""
    pct = f"{deal.discount * 100:.0f}%"
    record = ""
    if deal.is_record:
        record = f"""
    <tr><td colspan="2" style="padding-top:12px;">
      <span style="display:inline-block;padding:3px 9px;background:{AMBER};
          font-family:{SANS};font-size:11px;font-weight:600;color:{INK};">
        Lowest fare since tracking began</span>
    </td></tr>"""
    return f"""
<tr><td style="background:{INK};padding:22px 24px 20px 24px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td style="font-family:{SERIF};font-size:31px;line-height:34px;color:{AMBER};">
        {deal.city}
      </td>
      <td align="right" style="font-family:{SANS};font-size:31px;line-height:34px;
          font-weight:700;color:#FFFFFF;letter-spacing:-0.5px;white-space:nowrap;">
        {_money(deal.price)}
      </td>
    </tr>
    <tr>
      <td style="padding-top:6px;font-family:{SANS};font-size:13px;color:#A9B4C6;">
        {config.ORIGIN} to {deal.dest}, return
      </td>
      <td align="right" style="padding-top:6px;font-family:{SANS};font-size:13px;
          color:{AMBER};white-space:nowrap;">
        {pct} under its usual {_money(deal.baseline)}
      </td>
    </tr>{record}
  </table>
</td></tr>"""


def _summary(deal: Deal) -> str:
    q = deal.best
    stops = "non-stop" if q.stops == 0 else f"{q.stops} stop" + ("s" if q.stops > 1 else "")
    route = " · ".join(f"{l.origin}–{l.dest} {l.airline}{l.number}" for l in q.outbound)
    back = ""
    if q.inbound:
        back = " · ".join(f"{l.origin}–{l.dest} {l.airline}{l.number}" for l in q.inbound)

    rows = [
        ("Airline", _airlines(q.airlines)),
        ("Routing", f"{stops}, {_hm(q.total_minutes)} in the air"),
        ("Outbound", route),
    ]
    if back:
        rows.append(("Return", back))
    if q.outbound and q.outbound[0].aircraft:
        rows.append(("Aircraft", q.outbound[0].aircraft))
    rows.append(("Flexibility", f"{deal.option_count} date combinations at or near this fare"))

    body = "".join(f"""
    <tr>
      <td width="84" valign="top" style="padding:5px 12px 5px 0;font-family:{SANS};
          font-size:12px;color:{SLATE};">{label}</td>
      <td valign="top" style="padding:5px 0;font-family:{SANS};font-size:13px;
          line-height:19px;color:{INK};">{value}</td>
    </tr>""" for label, value in rows)

    return f"""
<tr><td style="padding:18px 24px 6px 24px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{body}</table>
</td></tr>"""


def _timetable(deal: Deal) -> str:
    """The grid, grouped by fare. This is the part worth reading twice."""
    blocks = []
    for i, tier in enumerate(deal.tiers):
        lo, hi = tier.nights_range
        if lo == hi:
            length = f"{lo} nights"
        else:
            length = f"{lo} to {hi} nights, your pick"

        heading = f"""
      <tr><td colspan="4" style="padding:{'14' if i else '4'}px 0 6px 0;
          border-bottom:1px solid {RULE};font-family:{SANS};font-size:12px;color:{SLATE};">
        <span style="color:{INK};font-weight:600;font-size:13px;">{_money(tier.price)}</span>
        &nbsp;&nbsp;{len(tier.options)} departures, {length}
      </td></tr>"""

        rows = []
        for j, o in enumerate(tier.options[:14]):
            bg = WASH if j % 2 else PAPER
            rows.append(f"""
      <tr>
        <td style="background:{bg};padding:7px 8px 7px 8px;font-family:{SANS};
            font-size:13px;color:{INK};white-space:nowrap;">{_pretty(o.depart_date)}</td>
        <td style="background:{bg};padding:7px 8px;font-family:{SANS};
            font-size:13px;color:{INK};white-space:nowrap;">{_pretty(o.return_date)}</td>
        <td style="background:{bg};padding:7px 8px;font-family:{SANS};
            font-size:12px;color:{SLATE};white-space:nowrap;">{o.nights} nights, {o.weekday_pair}</td>
        <td align="right" style="background:{bg};padding:7px 8px 7px 0;font-family:{SANS};
            font-size:12px;white-space:nowrap;">
          <a href="{o.url}" style="color:{INK};text-decoration:underline;">Open</a></td>
      </tr>""")

        extra = ""
        if len(tier.options) > 14:
            extra = f"""
      <tr><td colspan="4" style="padding:6px 8px;font-family:{SANS};font-size:12px;
          color:{SLATE};">and {len(tier.options) - 14} more dates at this fare</td></tr>"""

        blocks.append(heading + "".join(rows) + extra)

    return f"""
<tr><td style="padding:10px 24px 4px 24px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    {''.join(blocks)}
  </table>
</td></tr>"""


def _confidence(deal: Deal) -> str:
    if deal.season:
        scope = f"{deal.season} departures on this route"
    else:
        scope = "this route, all seasons mixed"
    if deal.history_days < 7:
        note = (f"Baseline from {deal.history_days} day(s) of tracking {scope} — thin. "
                f"Sanity-check this one against Google Flights before booking.")
    else:
        note = f"Baseline from {deal.history_days} days of tracking {scope}."
    return f"""
<tr><td style="padding:10px 24px 26px 24px;font-family:{SANS};font-size:12px;
    line-height:17px;color:{SLATE};border-bottom:3px solid {INK};">{note}</td></tr>"""


# ---------------------------------------------------------------- document


def html(deals: list[Deal], scanned: int, started: datetime) -> str:
    today = started.strftime("%A %d %B %Y").replace(" 0", " ") if hasattr(started, "strftime") else ""
    bar = int(config.DISCOUNT_FLOOR * 100)
    if config.MAX_STOPS is None:
        stops = "any number of stops"
    else:
        stops = f"max {config.MAX_STOPS} stop{'s' if config.MAX_STOPS != 1 else ''}"

    if deals:
        lede = (f"{len(deals)} fare{'s' if len(deals) > 1 else ''} at least {bar}% "
                f"below normal, out of {scanned} routes checked.")
    else:
        lede = f"Nothing {bar}% below normal today. {scanned} routes checked."

    body = "".join(
        _board(d) + _summary(d) + _timetable(d) + _confidence(d) for d in deals
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
<title>Fares from {config.ORIGIN}</title></head>
<body style="margin:0;padding:0;background:#EDE9E0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#EDE9E0;">
<tr><td align="center" style="padding:20px 10px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
       style="width:600px;max-width:100%;background:{PAPER};">

  <tr><td style="padding:24px 24px 18px 24px;border-bottom:3px solid {INK};">
    <div style="font-family:{SERIF};font-size:20px;color:{INK};">
      Fares from {config.ORIGIN}</div>
    <div style="padding-top:5px;font-family:{SANS};font-size:13px;color:{SLATE};">
      {today}</div>
    <div style="padding-top:10px;font-family:{SANS};font-size:14px;line-height:20px;
        color:{INK};">{lede}</div>
  </td></tr>

  {body}

  <tr><td style="padding:18px 24px 24px 24px;font-family:{SANS};font-size:11px;
      line-height:16px;color:{SLATE};">
    Prices in {config.CURRENCY} for one adult, {config.CABIN.replace('-', ' ')},
    {stops}. Fares move hourly and these were read once this
    morning — open a link to confirm before you book. Nothing here is a booking
    or a hold.
  </td></tr>

</table></td></tr></table></body></html>"""


def text(deals: list[Deal], scanned: int) -> str:
    """For clients that won't render HTML, and for reading the log."""
    out = [f"Fares from {config.ORIGIN} — {date.today().isoformat()}",
           f"{len(deals)} deals from {scanned} routes", ""]
    for d in deals:
        out.append(f"{d.city} ({d.dest}) — {_money(d.price)} "
                   f"({d.discount * 100:.0f}% off {_money(d.baseline)})")
        out.append(f"  {_airlines(d.best.airlines)}, {d.best.stops} stop(s)")
        for tier in d.tiers:
            out.append(f"  {_money(tier.price)}:")
            for o in tier.options[:14]:
                out.append(f"    {o.depart_date} to {o.return_date} "
                           f"({o.nights}n)  {o.url}")
        out.append("")
    return "\n".join(out)


def subject(deals: list[Deal]) -> str:
    if not deals:
        return f"No fares cleared the bar from {config.ORIGIN}"
    top = deals[0]
    head = f"{top.city} {_money(top.price)}, {top.discount * 100:.0f}% off"
    if len(deals) > 1:
        head += f" (+{len(deals) - 1} more)"
    return head
