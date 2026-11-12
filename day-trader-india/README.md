# The Day Trader skill, India edition

11 Claude skills for day trading on NSE and BSE: scan thousands of charts, track breaking news, time every entry and exit, and replay every outcome before you risk a rupee.

A port of [Jake Schincariol's day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill)
(MIT) from the US market to the Indian one: IST and the 9:15 to 15:30 NSE
session, NSE holidays, rupees, NSE tick sizes, Indian intraday charges (STT,
stamp duty, GST...), MIS intraday orders and the broker's 15:20 square-off,
circuit limits, Zerodha's Kite connector, NSE announcements, and NSE bulk and
block deals in place of the US Congress tracker.

Free, no signup, no API key. The tools are plain Python 3.8+ (nothing to pip
install) that read free public data: Yahoo Finance charts (`.NS` / `.BO`),
NSE's symbol lists, announcements and deal files, Google News India.

And no trade goes through until you say yes. Nothing in this pack can place an
order on its own. Paper trading is the default, and in paper mode no broker is
called at all.

## Install

Copy the skill folders into your project's `.claude/skills/` (or into
`~/.claude/skills/` for every project):

```bash
cp -r day-trader-india/trader-* .claude/skills/
```

Then copy `trader-budget/config.example.json` to `trader/config.json` in your
project and set your budget and limits. As a plugin, point Claude Code's
`/plugin marketplace add` at the folder that holds `.claude-plugin/`.

## The eleven

| command | job | what it does |
| --- | --- | --- |
| `/trader-scanner` | Chart Scanner | Scans every NSE equity (or the Nifty 500) for setups: opening-range breakouts, flags, oversold bounces. |
| `/trader-news` | News Monitor | NSE announcements, Yahoo and Google News India headlines for every stock you watch. |
| `/trader-entry` | Entry Timer | Watches a setup bar by bar and tells you the moment to get in. |
| `/trader-exit` | Exit Planner | Sets your stop and your target on the NSE tick before you enter; flat by 15:15 IST. |
| `/trader-timemachine` | Time Machine | Replays the rest of the session 10,000 times plus every past time the setup fired. |
| `/trader-risk` | Risk Manager | Checks every trade against your limits, the entry window, circuit limits and charges. |
| `/trader-budget` | Budget Manager | Sizes every position to your budget and your max loss, charges included. |
| `/trader-broker` | Order Executor | Paper by default; live, the exact Kite calls, never without your yes. |
| `/trader-alerts` | Price Alerts | Rings when a price, a stop, the 9:15 bell or the 15:15 flat-by time hits. |
| `/trader-analyst` | Earnings Analyst | Quarterly results in crore, by Indian fiscal quarter, and what changed. |
| `/trader-deals` | Big-Money Tracker | NSE's bulk and block deals, by name, the evening they happen. |

## How to use it

Everything lands in a `trader/` folder in your project, and each skill reads
what the last one wrote:

```
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker   (one trade)
alerts: stop, target, flat by 15:15                                          (while it is open)
news / analyst / deals                                                        (on a schedule)
```

The demo trade, on synthetic data (`DEMO.NS`, real US bars moved onto the NSE
clock; see `tests/fixtures`), Monday October 19 2026:

1. **`/trader-scanner`** at 10:00 AM IST: of 231 usable charts, 42 had closed
   above their 15-minute opening range. DEMO: range ₹354.47 to ₹362.18.
2. **`/trader-news`**: an NSE board-meeting outcome (results) at 9:30, and an
   order-win headline. Results day: a day trade is out by 15:15.
3. **`/trader-entry`**: at 9:57 waiting (the 9:55 bar still open); at 10:00
   triggered, the 9:55 bar closed at ₹364.18.
4. **`/trader-exit`**: stop at the range midpoint rounded down to the 0.05
   tick, ₹358.30; risk ₹5.88; 1R target rounded up to the tick, ₹370.10; flat
   by 15:15.
5. **`/trader-timemachine`**: 10,000 replays to 15:15: target first 26.5 %,
   stop first 21.9 %, still open 51.6 %; the same rule on 57 past sessions
   fired 32 times, 12 target, 16 stop. Close to a coin flip.
6. **`/trader-budget`**: ₹1,00,000 account, ₹1,000 max loss: 159 shares
   (₹57,904.62). Loss at the stop ₹934.92 plus ₹60.80 of charges = ₹995.72.
7. **`/trader-risk`**: PASS (window 09:30 to 14:45, loss, reward:risk, cash, daily limits).
8. **`/trader-broker`**: the paper ticket; you type yes for that one order.
9. **`/trader-alerts`**: rings on the stop, the target and at 15:15 to flatten.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

They run offline on synthetic fixtures (fictional companies, or real US bars
renamed and moved onto the NSE clock: nothing in `tests/fixtures` is real NSE
data).

## Fine print

**Not financial advice.** This is software that reads public data and does
arithmetic. Nothing here comes from a SEBI-registered investment adviser or
research analyst. SEBI's own study of FY2023 found that about 7 in 10
individual intraday traders in the equity cash segment lost money. You can
lose money. Decide for yourself.

**No trade goes through until you say yes.** Only `/trader-broker` can lead to
an order, only after `/trader-risk` passes that exact order and you type yes
for it, and, live, only through Claude's own Allow once card with the
broker's order tools set to "Needs approval". No F&O, intraday leverage or
short selling unless you turn them on.

**Paper first.** `"paper": true` is the default and calls no broker. Kite has
no paper account: going live means real orders.

**Intraday rules.** MIS positions are squared off by the broker around 15:20
(with a charge); the pack aims to be flat by 15:15. Trade-for-trade (BE / BZ)
stocks cannot be day traded; ASM / GSM and F&O-ban stocks belong on your
blocked list. Stocks have daily price bands: a stop can fail to fill at a
circuit.

**Charges are estimates.** Brokerage, STT, exchange, SEBI, stamp duty and GST
rates are built in as of late 2026 and are overridable in the config. Check
your broker's contract note.

**Holidays and ticks.** The NSE 2026 holiday list and NSE's price-based tick
sizes are built in; add next year's holidays with `"extra_holidays"`, and
force a tick with `"tick_size"` if your broker rejects a price.

**The data is free and unofficial.** Yahoo's endpoints can lag, change or
rate-limit you, and NSE sometimes refuses scripted downloads (every tool
then says so and takes a saved file with `--offline`). The NSE announcement
and deal parsers, and the Yahoo fundamentals reader, were written without
live access to those feeds: check their first live run against the website.

**Taxes.** Intraday equity gains are speculative business income in India.
Nothing here is tax advice.

## Files

```
trader-scanner/     SKILL.md, scan.py
trader-news/        SKILL.md, news.py
trader-entry/       SKILL.md, entry.py
trader-exit/        SKILL.md, exit.py
trader-timemachine/ SKILL.md, timemachine.py
trader-risk/        SKILL.md, check.py
trader-budget/      SKILL.md, size.py, config.example.json, targets.example.json
trader-broker/      SKILL.md, ticket.py, claude_desktop_config.example.json
trader-alerts/      SKILL.md, alerts.py, alerts.example.json
trader-analyst/     SKILL.md, facts.py, metrics.example.json
trader-deals/       SKILL.md, deals.py
tests/              unittest suite + offline synthetic fixtures
```

MIT, like the original (see LICENSE).
