# Fares from YUL

A daily job that prices 200 routes out of Montréal (half of them each
day), works out what each one normally costs, and emails you only the fares
that are at least 40% below that. Each deal arrives with every date combination that sells at the same
price, so you pick the trip length instead of the fare picking it for you.

Personal tool. No server, no users, no accounts.

```
scan ──▶ ~100 routes × 11 sampled dates ──▶ price history (SQLite)
                                              │
                                    baseline: median of daily medians
                                              │
                          anything ≥28% under the baseline
                                              │
dive ──▶ top 7 routes × 19 departure dates × 7 trip lengths
                                              │
                          anything ≥40% under, saving ≥$250
                                              │
                                        email, or silence
```

## Setup

```bash
git clone <your repo> && cd vols
pip install -r requirements.txt
cp .env.example .env        # fill in Resend key + your address; read automatically
python run.py --preview     # writes preview.html, no network
python run.py --dry --only LIS,CDG   # real prices, two routes, no email
```

Then in your repo: add `RESEND_API_KEY` and `MAIL_TO` as Actions **secrets**,
`MAIL_FROM` and `ORIGIN` as Actions **variables**, and the cron in
`.github/workflows/fares.yml` takes it from there at 07:10 Montréal time.

Resend's free tier is 3,000 emails a month. Verify a domain you already own —
the shared `onboarding@resend.dev` sender only delivers to your own signup
address.

## The part that matters: what "40% off" is measured against

There is no published list price for a plane ticket, so the tool builds its
own reference. Every run samples eleven departure dates per route and stores
the median. The baseline is then the **median of the last 60 daily medians**.

Taking the median twice is deliberate. One anomalously cheap sampled date
can't drag the reference down, and neither can one anomalous day of scanning.
A route has to actually get cheaper, and stay cheaper, to move it.

**This means day one is the weak day.** With no history, the baseline falls
back to today's own scan, and a real sale depresses that scan slightly — so
the first week will both miss things and occasionally overstate a discount.
The email tells you how many days of history sit behind each number, and
flags anything under a week as thin. It's honest by about day 14 and solid by
day 30. Let it run for two weeks before you trust it.

`prices.db` is committed back to the repo after every run. That's not tidy,
but GitHub wipes the runner between jobs and the history is the whole product.
Delete it and you're back to day one.

## Tuning

Everything lives in `config.py`, all overridable by env var.

| | | |
|---|---|---|
| `DISCOUNT_FLOOR` | `0.40` | The bar. `0.50` for near-silence. |
| `MIN_ABS_SAVING` | `250` | Stops 40% off a $180 hop outranking 42% off Tokyo. |
| `MAX_PRICE` | `1600` | 55% off a $4k business fare is still not a deal. |
| `MAX_DEEP_DIVES` | `7` | Main cost lever. Each dive is ~130 requests. |
| `SCAN_SAMPLES` | `11` | Per route per scan. Raising this raises everything. |
| `SCAN_EVERY_DAYS` | `2` | Each route is scanned every N days. `1` = all daily, ~2× the run. |
| `TRIP_LENGTHS` | 5–21n | The nights offered in the grid. |
| `SEND_WHEN_EMPTY` | `0` | Set `1` if silence makes you distrust the cron. |

Adding destinations is the expensive edit: each one costs 11 requests every
scan, forever. A few routes on the list only have one-stop service
seasonally; one that logs `no fares returned` for weeks is safe to delete.
Cutting the list to the places you'd actually go makes the run faster and
the email better.

## Runtime and blocking

With `SCAN_EVERY_DAYS=2`, roughly 1,100 scan requests plus ~900 dive
requests, paced 1.4–3.1s apart with jitter: **about 90 minutes**. The
workflow allows 240, and saves `prices.db` even if a run dies part-way.
Keep the repo public: Actions minutes are free there, and a private repo
would burn through the 2,000 free minutes in three weeks.

`fast_flights` reads Google Flights by reconstructing its private protobuf
query — no key, no quota, no terms you've agreed to. In practice a paced
once-daily run of this size is unremarkable traffic. If Google starts
refusing, `flights.Blocked` is raised, the run stops early rather than
hammering, and you get an email with whatever it found first. Lengthen
`REQUEST_DELAY` and cut `MAX_DEEP_DIVES` before trying anything cleverer.

The real fragility is the schema: Google changes its internal format
occasionally and the library needs a release to catch up. When prices stop
coming back, bump the `faster-flights` pin in `requirements.txt` first.
(`faster-flights` is a one-person fork of `fast-flights`; it's used because
the original lacks `get_return_flights`, `select_flight` and diagnostics.)

## Swapping the data source

Everything that knows about Google lives in `flights.py`. Three functions —
`price()`, `scan()`, `dive()` — returning `Quote` objects. Nothing downstream
knows or cares where they came from.

- **SerpApi** (`engine=google_flights`, $25/mo for 1,000 searches) also
  returns `price_insights` with Google's own typical price range, which
  could replace the whole baseline mechanism.
- **Travelpayouts Aviasales Data API** (free, affiliate signup) returns the
  cheapest fare for every day of a month in *one* call. That would collapse
  the scan pass from 420 requests to ~38. The data is cached from real user
  searches and up to 7 days stale, so it's a good screen and a bad quote —
  use it for `scan()` and keep Google for `dive()`.

## Files

| | |
|---|---|
| `run.py` | Orchestration, CLI, the two passes |
| `flights.py` | Google Flights. The only fragile file |
| `deals.py` | The bar, and grouping the grid into same-price tiers |
| `store.py` | SQLite, baselines, repeat-alert suppression |
| `render.py` | The email |
| `sample.py` | Fake deals for `--preview` |

## Things it deliberately doesn't do

Book anything, hold anything, or watch a route you've already booked. It
reads fares once a morning and they move hourly, so every price is a lead to
confirm, not a quote. One-way fares, multi-city, positioning flights and
error fares below the sampled dates are all out of scope.
