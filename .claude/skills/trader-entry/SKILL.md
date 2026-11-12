---
name: trader-entry
description: >-
  Entry Timer. Watches a setup bar by bar on NSE stocks and tells you the
  moment to get in: reads free Yahoo 1-minute or 5-minute bars (.NS),
  builds the opening range (9:15 to 9:30 IST by default) and calls the entry
  on the first completed bar that closes above the range high, or above a
  level you give it, with an optional volume check. Says waiting and how
  far, triggered with the time and the price, expired (no entries after
  14:45 IST), or not open yet, and writes trader/entry.json for /trader-exit.
  Long side only. It never places an order. Use when the user says "tell me
  when to get in", "watch RELIANCE", "has it broken out", "did it break the
  opening range", "entry signal", "time my entry", or after /trader-scanner
  and /trader-news, before /trader-exit.
argument-hint: "[symbol] [--setup orb|level] [--interval 5m|1m]"
---

# trader-entry

The entry timer turns a setup into one moment: the bar that confirms it. It
reads bars and waits for each one to finish. A price that pokes above the
high in the middle of a bar is not an entry. A bar that closes above it is.
Then it says the time and the price, writes them down for the exit planner,
and stops. It never buys anything. Day trading loses most people money, and
a clean signal does not change that.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE              # 15-minute opening range, 5-minute bars
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE --write      # also save trader/entry.json
python3 "${CLAUDE_SKILL_DIR}/entry.py" check INFY --setup level --level 1512.40
python3 "${CLAUDE_SKILL_DIR}/entry.py" check TCS --interval 1m --min-volume-x 1.5
python3 "${CLAUDE_SKILL_DIR}/entry.py" watch RELIANCE --until 14:45  # one line per closed bar, stops on the trigger
python3 "${CLAUDE_SKILL_DIR}/entry.py" watchlist                   # every hit in trader/watchlist.json
```

Other flags: `--or-minutes N` (15), `--json`, `--offline FILE`, `--now "2026-10-19 10:00"`
(IST) to replay a day. `watch` with `--now` or `--offline` runs on a simulated
clock and replays the day bar by bar without waiting.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/watchlist.json` | the scanner's hits, for `watchlist` |
| `trader/config.json` | `no_entries_before` (09:30), `no_entries_after` (14:45), IST; `exchange`; `extra_holidays` |
| Yahoo chart API | today's bars, `RELIANCE.NS`, `range=1d&interval=5m` (or `1m`): free, unofficial, can lag |
| `trader/entry.json` | with `check --write`, or when `watch` triggers |

## The rule

- **Opening range (orb).** The high and low of the 9:15, 9:20 and 9:25 five-minute
  bars (or fifteen 1-minute bars). The level to beat is the range high.
- **The trigger** is the first completed bar after the range that closes above
  the level. A wick above is not a trigger; a close exactly at it is not above.
- **The time** is that bar's close time (the 9:55 bar closes at 10:00 AM). The
  price is its close, to the paisa.
- **Only closed bars count**, and only once Yahoo has caught up to that moment.
- **Volume, if you want it.** `--min-volume-x 1.5` also needs 1.5 times the range
  bars' average volume. The 9:15 bar carries the pre-open auction's matched
  orders, so 1.0 is already strict.
- **Time limits.** No entries before 9:30 or after 14:45 IST, so there is time to
  manage the trade before the broker squares off intraday positions around 15:20.
- **Closed days.** Weekends and NSE holidays (Dussehra, Diwali Balipratipada...).

## Steps

1. Get the symbol, or run `entry.py watchlist` after `/trader-scanner`. Check
   `/trader-news` for it first.
2. Run `entry.py check SYMBOL` and say the status in one line.
3. To wait for it, Claude can run `entry.py watch SYMBOL --until 14:45` in the
   background, or `entry.py check SYMBOL --write` on a `/loop` every 5 minutes.
   Keep the computer awake: a sleeping laptop catches up late.
4. When it triggers, say the time and the price, and that nothing was placed.
   If the trigger is more than a bar old, say that too: a late entry is a
   different trade.
5. Hand off to `/trader-exit` to set the stop and target before anything is bought.

## Example: the demo

DEMO (synthetic), Monday 2026-10-19, opening range ₹354.47 to ₹362.18. At 9:57
the 9:55 bar is still open:

```
WAITING  last close ₹361.68 (9:50 bar), ₹0.50 under the range high ₹362.18 (-0.14%).
The 9:55 bar is still forming (₹364.18 so far, closes 10:00 AM); it does not count until it closes.
```

At 10:00 AM:

```
TRIGGERED 10:00 AM at ₹364.18: the 9:55 bar (bar 8) closed above the range high ₹362.18 (+0.55%).
This is the moment to get in, if you take the trade. Nothing was placed.
```

With `--min-volume-x 1` the 9:55 bar is too thin and the trigger moves to
10:20 AM at ₹365.75 (the 10:15 bar, 7.98x the range's volume).

## Rules

- Bar by bar, on free Yahoo bars. They are unofficial and can lag.
- A signal is information, not an order and not a promise.
- Long side only: v2 plans longs only. An intraday short in India needs a
  broker that allows it and is off in this pack.
- One trigger per setup per day.

## What it never does

It never places an order, never sizes a position, never sets the stop, and
never runs `/trader-broker` from a background watch: nobody is there to say yes.

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
