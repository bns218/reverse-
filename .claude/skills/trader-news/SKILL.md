---
name: trader-news
description: >-
  News Monitor for Indian stocks. Tracks breaking news on every stock you
  watch and flags what moves it: NSE corporate announcements (board-meeting
  outcomes and results, resignations, credit ratings, acquisitions,
  insolvency), Yahoo Finance India and Google News India headlines, and how
  far each stock is from yesterday's close. Shows only what is new since the
  last check, newest first, in IST, tagged (results, analyst, SEBI and
  legal, promoter pledges and capital, orders, circuits and F&O ban, RBI and
  macro). Use when the user says "any news on RELIANCE", "what's moving",
  "why is it up", "check the news", "results today", or after
  /trader-scanner, before /trader-entry.
argument-hint: "[--tickers SYMBOL ...] [--hours N] [--all]"
---

# trader-news

The news monitor reads what the stock's own company told the exchange, and
what the papers are saying, for the stocks you care about. It shows each
item once. Headlines are leads, not facts: open the story, or the filing,
before acting on one.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                               # watchlist + plan + portfolio symbols
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE TCS INFY
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE --all --hours 72
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-filings --no-google     # Yahoo headlines only
```

## Sources

| source | what |
| --- | --- |
| NSE corporate announcements RSS | one request for the whole market, filtered to your companies: results, resignations, ratings, deals |
| Yahoo Finance headline RSS | per symbol (`RELIANCE.NS`, region IN) |
| Google News India search RSS | per company, by its name in quotes (from `trader/universe.txt`) |
| Yahoo chart | the move against yesterday's close |

An announcement with results, a resignation, a rating change, a deal, a
default or insolvency, a buyback or bonus, or a SEBI order gets the `!`
mark. NSE sometimes refuses scripted downloads; the tool says so and the
headlines still run. Company names matter: run `/trader-scanner universe`
once so `trader/universe.txt` has them.

## Steps

1. Run it on the scanner's hits or the symbol about to be traded.
2. Read back the `!` items first, then the rest, newest first, in IST.
3. Results due this week matter for a day trade: say so, and that a day trade
   is closed by 15:15, before an evening results announcement.
4. Say once: headlines are leads, not facts.

## Example: the demo (synthetic headlines)

```
DEMO       ₹366.48 +3.31% vs yesterday's close ₹354.72 at 10:37 IST  MOVING
! 2026-10-19 09:30 IST  DEMO        NSE filing    Demo Industries Limited: Outcome of Board Meeting - Financial Results ...
  2026-10-19 08:34 IST  DEMO        Yahoo Finance Demo Industries Q2 results preview: net profit seen up 12%
  2026-10-19 07:40 IST  DEMO        Example Business Daily Demo Industries bags order worth Rs 450 crore ...
```

## Rules

- Quote the source and the link; never retell a rumour as fact.
- Tags are keyword matches, not judgments.
- Not financial advice.

## What it never does

It never trades on a headline, never scores news as bullish or bearish, and
never reads paywalled stories.

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
