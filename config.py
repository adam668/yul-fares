"""Everything you'd want to tune lives here."""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(name: str = ".env") -> None:
    """Read KEY=value lines from .env into the environment for local runs.

    Real environment variables win, so Actions secrets are never shadowed
    by a stray file. Twenty lines of parsing isn't worth a dependency.
    """
    path = Path(__file__).with_name(name)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv()

# ---------------------------------------------------------------- basics

ORIGIN = os.getenv("ORIGIN", "YUL")
CURRENCY = os.getenv("CURRENCY", "CAD")
LANGUAGE = "en-US"          # affects Google's response parsing, not your email
CABIN = "economy"
MAX_STOPS = 1               # 2-stop fares are cheap and miserable; None to allow all

# ---------------------------------------------------------------- the bar

# A deal must be at least this far below the route's normal price.
DISCOUNT_FLOOR = float(os.getenv("DISCOUNT_FLOOR", "0.40"))   # 40% off

# ...and must save at least this much in absolute terms, so 40% off a
# $180 hop to Boston doesn't crowd out 45% off a $1,400 fare to Tokyo.
MIN_ABS_SAVING = float(os.getenv("MIN_ABS_SAVING", "250"))

# Hard ceiling. Even a 60%-off business-class fare isn't a "deal" if it's $3k.
MAX_PRICE = float(os.getenv("MAX_PRICE", "1600"))

# How many routes get the expensive deep-dive each run.
MAX_DEEP_DIVES = int(os.getenv("MAX_DEEP_DIVES", "7"))

# ---------------------------------------------------------------- horizon

SCAN_START_DAYS = 21        # ignore the next 3 weeks; fares there are never cheap
SCAN_END_DAYS = 300         # ~10 months out
SCAN_SAMPLES = int(os.getenv("SCAN_SAMPLES", "11"))   # departure dates per route

# Scan each route once every N days, a different share of the list each
# run. 2 halves the run time and the traffic; each route still gets 30
# day-medians inside the 60-day baseline window. 1 scans everything daily.
SCAN_EVERY_DAYS = int(os.getenv("SCAN_EVERY_DAYS", "2"))

# Deep dive: how far either side of the cheap date to sweep, and which
# trip lengths to price. This grid is what produces the "same price,
# pick your length" block in the email.
DIVE_RADIUS_DAYS = 18
DIVE_STEP_DAYS = 2
TRIP_LENGTHS = [5, 7, 9, 11, 14, 17, 21]

# ---------------------------------------------------------------- politeness

REQUEST_DELAY = (1.4, 3.1)  # random sleep between calls, seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 8.0         # seconds, doubled each retry

# ---------------------------------------------------------------- delivery

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
MAIL_FROM = os.getenv("MAIL_FROM", "deals@example.com")
MAIL_TO = os.getenv("MAIL_TO", "")
SEND_WHEN_EMPTY = os.getenv("SEND_WHEN_EMPTY", "0") == "1"

DB_PATH = os.getenv("DB_PATH", "prices.db")

# ---------------------------------------------------------------- routes
#
# (IATA, display name, region). Every destination costs SCAN_SAMPLES
# requests each time it's scanned. All of these are reachable from YUL
# with at most one stop on some carrier, but a few only seasonally — a
# route that logs "no fares returned" for weeks is safe to delete.

DESTINATIONS: list[tuple[str, str, str]] = [
    # Europe
    ("LIS", "Lisbon", "Europe"),
    ("OPO", "Porto", "Europe"),
    ("FAO", "Faro", "Europe"),
    ("FNC", "Madeira", "Europe"),
    ("PDL", "Azores", "Europe"),
    ("MAD", "Madrid", "Europe"),
    ("BCN", "Barcelona", "Europe"),
    ("AGP", "Málaga", "Europe"),
    ("SVQ", "Seville", "Europe"),
    ("VLC", "Valencia", "Europe"),
    ("BIO", "Bilbao", "Europe"),
    ("PMI", "Mallorca", "Europe"),
    ("IBZ", "Ibiza", "Europe"),
    ("TFS", "Tenerife", "Europe"),
    ("LPA", "Gran Canaria", "Europe"),
    ("CDG", "Paris", "Europe"),
    ("NCE", "Nice", "Europe"),
    ("LYS", "Lyon", "Europe"),
    ("MRS", "Marseille", "Europe"),
    ("TLS", "Toulouse", "Europe"),
    ("BOD", "Bordeaux", "Europe"),
    ("NTE", "Nantes", "Europe"),
    ("BRU", "Brussels", "Europe"),
    ("AMS", "Amsterdam", "Europe"),
    ("DUB", "Dublin", "Europe"),
    ("LHR", "London", "Europe"),
    ("EDI", "Edinburgh", "Europe"),
    ("MAN", "Manchester", "Europe"),
    ("FCO", "Rome", "Europe"),
    ("MXP", "Milan", "Europe"),
    ("VCE", "Venice", "Europe"),
    ("FLR", "Florence", "Europe"),
    ("NAP", "Naples", "Europe"),
    ("BRI", "Bari", "Europe"),
    ("CTA", "Catania", "Europe"),
    ("PMO", "Palermo", "Europe"),
    ("MLA", "Malta", "Europe"),
    ("ZRH", "Zurich", "Europe"),
    ("GVA", "Geneva", "Europe"),
    ("FRA", "Frankfurt", "Europe"),
    ("MUC", "Munich", "Europe"),
    ("BER", "Berlin", "Europe"),
    ("VIE", "Vienna", "Europe"),
    ("PRG", "Prague", "Europe"),
    ("BUD", "Budapest", "Europe"),
    ("WAW", "Warsaw", "Europe"),
    ("KRK", "Kraków", "Europe"),
    ("CPH", "Copenhagen", "Europe"),
    ("OSL", "Oslo", "Europe"),
    ("ARN", "Stockholm", "Europe"),
    ("HEL", "Helsinki", "Europe"),
    ("KEF", "Reykjavík", "Europe"),
    ("RIX", "Riga", "Europe"),
    ("TLL", "Tallinn", "Europe"),
    ("VNO", "Vilnius", "Europe"),
    ("ATH", "Athens", "Europe"),
    ("JTR", "Santorini", "Europe"),
    ("JMK", "Mykonos", "Europe"),
    ("HER", "Crete", "Europe"),
    ("SKG", "Thessaloniki", "Europe"),
    ("SPU", "Split", "Europe"),
    ("DBV", "Dubrovnik", "Europe"),
    ("ZAG", "Zagreb", "Europe"),
    ("LJU", "Ljubljana", "Europe"),
    ("BEG", "Belgrade", "Europe"),
    ("TIA", "Tirana", "Europe"),
    ("SOF", "Sofia", "Europe"),
    ("OTP", "Bucharest", "Europe"),
    ("IST", "Istanbul", "Europe"),
    ("AYT", "Antalya", "Europe"),
    ("LCA", "Cyprus", "Europe"),
    ("TBS", "Tbilisi", "Europe"),
    # Africa
    ("CMN", "Casablanca", "Africa"),
    ("RAK", "Marrakech", "Africa"),
    ("TUN", "Tunis", "Africa"),
    ("ALG", "Algiers", "Africa"),
    ("CAI", "Cairo", "Africa"),
    ("HRG", "Hurghada", "Africa"),
    ("DSS", "Dakar", "Africa"),
    ("ABJ", "Abidjan", "Africa"),
    ("ACC", "Accra", "Africa"),
    ("LOS", "Lagos", "Africa"),
    ("DLA", "Douala", "Africa"),
    ("ADD", "Addis Ababa", "Africa"),
    ("NBO", "Nairobi", "Africa"),
    ("KGL", "Kigali", "Africa"),
    ("EBB", "Entebbe", "Africa"),
    ("JRO", "Kilimanjaro", "Africa"),
    ("ZNZ", "Zanzibar", "Africa"),
    ("JNB", "Johannesburg", "Africa"),
    ("CPT", "Cape Town", "Africa"),
    ("WDH", "Windhoek", "Africa"),
    ("MRU", "Mauritius", "Africa"),
    ("SEZ", "Seychelles", "Africa"),
    # Middle East
    ("TLV", "Tel Aviv", "Middle East"),
    ("AMM", "Amman", "Middle East"),
    ("BEY", "Beirut", "Middle East"),
    ("DXB", "Dubai", "Middle East"),
    ("AUH", "Abu Dhabi", "Middle East"),
    ("DOH", "Doha", "Middle East"),
    ("MCT", "Muscat", "Middle East"),
    # Mexico & Central America
    ("MEX", "Mexico City", "Latin America"),
    ("CUN", "Cancún", "Latin America"),
    ("PVR", "Puerto Vallarta", "Latin America"),
    ("SJD", "Los Cabos", "Latin America"),
    ("OAX", "Oaxaca", "Latin America"),
    ("MID", "Mérida", "Latin America"),
    ("HUX", "Huatulco", "Latin America"),
    ("GDL", "Guadalajara", "Latin America"),
    ("BZE", "Belize City", "Latin America"),
    ("GUA", "Guatemala City", "Latin America"),
    ("SAL", "San Salvador", "Latin America"),
    ("RTB", "Roatán", "Latin America"),
    ("MGA", "Managua", "Latin America"),
    ("SJO", "San José CR", "Latin America"),
    ("LIR", "Liberia CR", "Latin America"),
    ("PTY", "Panama City", "Latin America"),
    # Caribbean
    ("PUJ", "Punta Cana", "Caribbean"),
    ("POP", "Puerto Plata", "Caribbean"),
    ("SDQ", "Santo Domingo", "Caribbean"),
    ("HAV", "Havana", "Caribbean"),
    ("VRA", "Varadero", "Caribbean"),
    ("HOG", "Holguín", "Caribbean"),
    ("CCC", "Cayo Coco", "Caribbean"),
    ("MBJ", "Montego Bay", "Caribbean"),
    ("KIN", "Kingston", "Caribbean"),
    ("NAS", "Nassau", "Caribbean"),
    ("PLS", "Turks and Caicos", "Caribbean"),
    ("GCM", "Grand Cayman", "Caribbean"),
    ("SJU", "San Juan", "Caribbean"),
    ("SXM", "St. Maarten", "Caribbean"),
    ("ANU", "Antigua", "Caribbean"),
    ("PTP", "Guadeloupe", "Caribbean"),
    ("FDF", "Martinique", "Caribbean"),
    ("UVF", "St. Lucia", "Caribbean"),
    ("BGI", "Barbados", "Caribbean"),
    ("GND", "Grenada", "Caribbean"),
    ("POS", "Trinidad", "Caribbean"),
    ("AUA", "Aruba", "Caribbean"),
    ("CUR", "Curaçao", "Caribbean"),
    # South America
    ("BOG", "Bogotá", "Latin America"),
    ("CTG", "Cartagena", "Latin America"),
    ("MDE", "Medellín", "Latin America"),
    ("UIO", "Quito", "Latin America"),
    ("GYE", "Guayaquil", "Latin America"),
    ("LIM", "Lima", "Latin America"),
    ("GRU", "São Paulo", "Latin America"),
    ("GIG", "Rio de Janeiro", "Latin America"),
    ("SSA", "Salvador", "Latin America"),
    ("EZE", "Buenos Aires", "Latin America"),
    ("MVD", "Montevideo", "Latin America"),
    ("SCL", "Santiago", "Latin America"),
    # Asia
    ("NRT", "Tokyo", "Asia"),
    ("KIX", "Osaka", "Asia"),
    ("ICN", "Seoul", "Asia"),
    ("PEK", "Beijing", "Asia"),
    ("PVG", "Shanghai", "Asia"),
    ("HKG", "Hong Kong", "Asia"),
    ("TPE", "Taipei", "Asia"),
    ("MNL", "Manila", "Asia"),
    ("BKK", "Bangkok", "Asia"),
    ("HKT", "Phuket", "Asia"),
    ("SGN", "Ho Chi Minh City", "Asia"),
    ("HAN", "Hanoi", "Asia"),
    ("KUL", "Kuala Lumpur", "Asia"),
    ("SIN", "Singapore", "Asia"),
    ("CGK", "Jakarta", "Asia"),
    ("DPS", "Bali", "Asia"),
    ("DEL", "Delhi", "Asia"),
    ("BOM", "Mumbai", "Asia"),
    ("BLR", "Bangalore", "Asia"),
    ("COK", "Kochi", "Asia"),
    ("CMB", "Colombo", "Asia"),
    ("KTM", "Kathmandu", "Asia"),
    ("MLE", "Maldives", "Asia"),
    # Pacific
    ("HNL", "Honolulu", "Pacific"),
    ("OGG", "Maui", "Pacific"),
    ("SYD", "Sydney", "Pacific"),
    ("MEL", "Melbourne", "Pacific"),
    ("BNE", "Brisbane", "Pacific"),
    ("AKL", "Auckland", "Pacific"),
    ("NAN", "Fiji", "Pacific"),
    ("PPT", "Tahiti", "Pacific"),
    # North America
    ("YVR", "Vancouver", "North America"),
    ("YYC", "Calgary", "North America"),
    ("YHZ", "Halifax", "North America"),
    ("YYT", "St. John's", "North America"),
    ("JFK", "New York", "North America"),
    ("ORD", "Chicago", "North America"),
    ("MIA", "Miami", "North America"),
    ("MCO", "Orlando", "North America"),
    ("MSY", "New Orleans", "North America"),
    ("AUS", "Austin", "North America"),
    ("DEN", "Denver", "North America"),
    ("LAS", "Las Vegas", "North America"),
    ("LAX", "Los Angeles", "North America"),
    ("SAN", "San Diego", "North America"),
    ("SFO", "San Francisco", "North America"),
    ("SEA", "Seattle", "North America"),
    ("ANC", "Anchorage", "North America"),
]
