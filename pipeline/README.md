# UFC Stats app – data pipeline (self-updating)

The site (`index.html` + `data.json` at the repo root) is rebuilt by GitHub Actions: **`.github/workflows/update-data.yml`**.

| When (CST, Saskatoon) | Mode | What |
|---|---|---|
| Daily ~5:37 AM | full | UFCStats fight data, UFC.com events/results/rankings/athlete pages, news feeds, odds → rebuild |
| Sat ~5:37 PM, Sun ~12:37 AM | full | fight-night card changes and results |
| Every 3 h (hourly Fri/Sat UTC) | odds | BestFightOdds lines; publishes only if a line moved |
| Any time | either | Actions tab → *Update data* → *Run workflow* |

`python3 pipeline/run.py full|odds` runs the same thing locally (stdlib Python + curl).

Steps (all in `pipeline/app/`): `update_mirror.py` (UFCStats CSVs from the public Greco1899 scrape) → `fetch_sources.py`
(UFC.com) → `fetch_news.py` (RSS headlines naming app fighters + `news_manual.json`) → `refresh_odds.py` (BestFightOdds)
→ `build_app_data.py` (ratings via `ratings.py`/`elo.py`/`areas.py`, stats estimate via `fit_overall.py`) → `make_html.py`
(`ufc-stats-app.html` + `data.json`). The page embeds its data (works offline) and re-checks `data.json` on load, reloading
once if a newer build exists.

**Safety.** Listing pages are validated before they replace the cached copy; mirror CSVs only replace the current copy when
the header matches and rows did not shrink. After building, `run.py` compares with the last published `data.json` and refuses
to publish (restores the old files, exits 1 → failed run, red X in Actions) if there are no events, an event has no bouts,
the first event is in the past, <10 ranking divisions, <60% of fighters rated, fighter count down >20%, or odds coverage
collapsed.

**Health check.** `health_check.py` runs after every run (even failed ones) and keeps one issue labelled `data-health` open
listing: failed/aborted runs, scraper or feed failures and layout changes, stale UFCStats data, missing odds for fights in the
next 10 days, card fighters (next 21 days) missing height/reach/age/record/rating/stats, unlinked (TBD) fighters, and short
rankings lists. The issue closes itself when the list is empty.

Sources are public pages only, fetched ~1 request every 0.5–2 s with an identifying user agent. Unofficial fan app.
Ratings/model docs: `app/README.md`. Analyst technical scores in `fighters/` are score tables only.

## Parlay builder (event page → *Parlay builder*)
Computed in the page from each data refresh, so it updates with every workflow run. A leg is eligible only when the stats
estimate and the no-vig market pick the same winner. Leg % = 40% stats + 60% market, minus penalties: pick out 730+ days
(−6), opponent out 730+ days (−2), pick with <2 UFC fights (−4), opponent <2 (−2), stats/market gap over 15 pts
(−half the excess). Ranking = historical win rate of similar legs (shrunk toward the leg %), tie-break on leg % then style
(striking differential, takedowns vs opponent TDD, last-3 form). Combined % = product (correlation ignored); odds = product of
median decimal lines. Historical rates: `app/parlay_calib.py` → `app/parlay_calib.json` (legs on UFC fights 2022+ joined
with public closing odds from `sources/parlay-hist.csv`; buckets = band × agreement (within 10 pts or not) × risk flags,
shown when n ≥ 40). Re-run it by hand only if the leg rule or rating model changes. For fun/info, not betting advice.
