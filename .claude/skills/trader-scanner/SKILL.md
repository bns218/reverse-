---
name: trader-scanner
description: >-
  Chart Scanner for the Indian market. Scans every NSE equity (or an index like
  the Nifty 500) for day-trading setups: before the open, daily-chart setups
  (20-day breakouts, bull flags, a reclaimed 20-day average, oversold and
  oversold bounces); after 9:30 AM IST, opening-range breakouts on 5-minute
  bars. Free Yahoo Finance data (.NS symbols), NSE's own symbol list, no key.
  Writes trader/watchlist.json for the news monitor and the entry timer. Use
  when the user says "scan the market", "what's breaking out", "find setups",
  "opening range breakout", "ORB scan", "scan Nifty 500", "pre-market scan",
  or at the start of a trading day, before /trader-news and /trader-entry.
argument-hint: "[universe|daily|orb] [--index nifty500] [--at HH:MM]"
---

# trader-scanner

The scanner looks at every chart so nobody has to. It does not pick stocks:
it lists the charts that match a rule, and the rest of the pack decides what,
if anything, to do with one of them.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                     # NSE's EQUITY_L.csv, series EQ -> trader/universe.txt
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe --index nifty500    # or only an index's stocks (niftyindices.com)
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                        # before 9:15 AM IST: daily setups
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb                          # after 9:35 AM IST: opening-range breakouts so far
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --at 10:00 --symbols RELIANCE,TCS,INFY
```

Other flags: `--watchlist FILE`, `--limit N`, `--min-price` (Rs 50), `--min-volume`
(500,000 shares, daily), `--or-minutes 15`, `--max-confirm 200`, `--json`,
`--offline FILE`, `--now "2026-10-19 10:00"` (IST) to replay a day.

## What it reads and writes

| file | what |
| --- | --- |
| NSE `EQUITY_L.csv` or a niftyindices.com constituents CSV | the universe (`universe`) |
| `trader/universe.txt` | one `SYMBOL|Company Name` a line; the news monitor uses the names |
| Yahoo spark and v8 chart (`RELIANCE.NS`) | daily closes and 5-minute bars: free, unofficial, can lag |
| `trader/config.json` | `exchange` (NSE, or BSE for `.BO`), `no_entries_after` (14:45) |
| `trader/watchlist.json` | the hits, for `/trader-news` and `/trader-entry watchlist` |

## The universe

Series EQ only, by default. BE and BZ stocks are trade-for-trade: every trade
must be delivered, so they cannot be day traded. SM and ST are SME platform
stocks. Symbols keep NSE's spelling (`M&M`, `BAJAJ-AUTO`); the tool adds
`.NS` for Yahoo. NSE sometimes refuses scripted downloads: then save
`EQUITY_L.csv` (or `ind_nifty500list.csv`) from a browser and run
`scan.py universe --offline FILE`. The full list is about 2,000 stocks, many
thin: a Nifty 500 universe is a sensible start.

## The rules

- **Session.** 9:15 to 15:30 IST. The 9:00 to 9:08 pre-open call auction sets
  the opening price but is not a bar of the range.
- **Opening range.** The first 15 minutes: the 9:15, 9:20 and 9:25 bars. A hit is
  the first completed 5-minute bar to CLOSE above the range high, timed at the
  bar's close. Stage 1 reads closes for everything; stage 2 confirms the
  candidates with real highs and lows, the most traded first.
- **Daily setups** use completed daily closes only; today's bar is dropped
  until 15:30.
- **Usable charts only.** A chart with a missing 5-minute bar (a halt, a
  circuit freeze, no trades) is left out and counted.
- **Holidays.** NSE's 2026 trading holidays are built in. NSE publishes the
  next year's list in December: add those dates to `"extra_holidays"` in
  `trader/config.json` until the tool is updated.

## Steps

1. If there is no `trader/universe.txt`, run `scan.py universe --index nifty500`.
2. Before the open run `scan.py daily`; after 9:35 AM IST run `scan.py orb`.
3. Read back the counts (fetched, usable, candidates) and the first hits.
   Say PARTIAL if stage 2 stopped at `--max-confirm`.
4. Hand one chart at a time to `/trader-news SYMBOL`, then `/trader-entry SYMBOL`.

## Example: the demo

On the synthetic Oct 19 2026 replay (234 charts, real US bars moved onto the
NSE clock and renamed; see `tests/fixtures`), `scan.py orb --at 10:00`:

```
Opening-range breakout scan, Mon 2026-10-19 10:00 AM IST: 15-minute range (9:15 to 9:30 AM), 5-minute bars, Yahoo.
Fetched 233 of 234 charts (1 failed or had no data); 231 usable; 95 candidates, 95 confirmed with real highs and lows.
42 of 231 charts closed above their opening-range high by 10:00 AM:
```

DEMO is one of them: range ₹354.47 to ₹362.18, the 9:55 bar closed at ₹364.18.

## Rules

- A scan is a list of charts that match a rule, not a list of stocks to buy.
- Never call a hit a tip, a call or a recommendation.
- Free data can lag and can be wrong: say so when a minute matters.

## What it never does

It never places an order, never ranks stocks by how much they will rise, and
never scans F&O contracts.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation, and nothing
  here comes from a SEBI-registered investment adviser or research analyst.
- Paper trading by default (`"paper": true`): no broker is called at all. Going live is the user's own
  decision, in their own config.
- Nothing in this pack places an order except trader-broker, and only when all three hold: trader-risk
  passed that exact order today, the user typed an explicit yes for that one order in the chat, and, for a
  live account, the user clicked Allow once on Claude's own card because the broker's order tool is set to
  "Needs approval" (Customize > Connectors > tool permissions). Never set an order tool to "Always allow".
- No F&O, intraday leverage (margin) or short selling unless the config allows it and the user confirms.
- Broker logins stay with the broker (Kite's own login page) or in the Claude Desktop config, never in
  the chat. Never ask for a password, a TOTP or an API secret.
