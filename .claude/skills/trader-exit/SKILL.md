---
name: trader-exit
description: >-
  Exit planner. Sets your stop and your target before you enter, so you know
  when to get out. Reads the entry from trader-entry (or a price you give),
  puts the stop at the opening-range midpoint by default (or the range low,
  your price, a percent, or a multiple of the ATR), rounds it down to the
  NSE tick, and sets the target at 2R (or 1R, or your price), rounded up to
  the tick. Refuses a stop at or above the entry, a target at or below it,
  or a stop too tight to survive the spread, and says why. Flat by 15:15 IST,
  before the broker's intraday (MIS) square-off. Writes trader/plan.json for
  the time machine, the budget manager and price alerts. Long side only. Use
  when the user says "where's my stop", "set my stop and target", "plan the
  exit", "stop loss", "what's my R", "risk reward", or right after
  /trader-entry triggers, before /trader-timemachine.
argument-hint: "[--stop or-mid|or-low|price:X|pct:X|atr:K] [--target 2R|1R|price:X]"
---

# trader-exit

The exit planner decides how a trade ends before it starts. The stop is
where the setup has failed. The target is where you take what you came for.
Both are set before the entry, written down and handed on, so nobody has to
decide anything in the middle of a fast move. A stop is a plan, not a
guarantee: a gap, a fast market or a circuit limit can fill past it, or stop
it filling at all. Day trading loses most people money, and a neat plan does
not change that.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan                          # trader/entry.json: midpoint stop, 2R target
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop or-mid --target 1R --write
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop atr:1.5           # needs the session's bars (Yahoo or --offline)
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol RELIANCE --entry 1412.50 --setup level --stop pct:1
python3 "${CLAUDE_SKILL_DIR}/exit.py" show                          # the current trader/plan.json
```

Other flags: `--flat-by 15:15`, `--json`, `--now "2026-10-19 10:01"` (IST),
`--entry PRICE` with a waiting entry.json to plan ahead, `--offline FILE`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/entry.json` | the trigger from trader-entry |
| `trader/config.json` | `flat_by` (15:15), `min_reward_risk` (1.0, a note here), `tick_size` ("nse"), `exchange` |
| Yahoo chart API | only for an `atr:K` stop |
| `trader/plan.json` | with `--write`: entry, stop, target, R, risk a share, flat by |

## Stops, targets and ticks

| stop | where it goes |
| --- | --- |
| `or-mid` | the opening-range midpoint (the default for an opening-range breakout) |
| `or-low` | the opening-range low: wider, so fewer shares for the same max loss |
| `price:X` | your price (`price:₹358.30` and `price:Rs 358.30` work too) |
| `pct:X` | X percent under the entry |
| `atr:K` | K times the 14-bar ATR under the entry |

- **Ticks.** Orders must sit on the exchange tick. NSE's price-based ticks:
  0.01 under ₹250, 0.05 to ₹1,000, 0.10 to ₹5,000, 0.50 to ₹10,000, 1.00 to
  ₹20,000, 5.00 above. Set `"tick_size": 0.05` in the config to force one if
  your broker rejects a price.
- **Rounding.** The stop rounds DOWN to the tick, away from the entry. An R
  target rounds UP to the tick, so the reward is never less than R times the
  risk; a price target rounds half up.
- **Refused, with the reason.** A stop at or above the entry, a target at or
  below it, a risk under 0.05% of the price (too tight to survive the spread),
  an entry that has not triggered (unless `--entry`), a short.
- **Flat by.** 15:15 IST by default: out by then, win or lose. Brokers square
  off MIS positions themselves around 15:20 and charge for it.

## Steps

1. Run it right after `/trader-entry` triggers (`--entry PRICE` plans ahead).
2. Use the default stop unless the user names another; a level setup needs one.
3. Run `exit.py plan --write` and read back the entry, stop, target, risk a
   share, reward:risk and flat by.
4. If it refuses, say the reason and the fix. Never loosen anything on your own.
5. Say once that the stop is a plan, not a guarantee.
6. Hand off to `/trader-timemachine`, then `/trader-budget`. Offer `/trader-alerts`.

## Example: the demo

DEMO (synthetic), Monday 2026-10-19: entry ₹364.18 at 10:00 AM (bar 8), opening
range 354.47 to 362.18. `exit.py plan --stop or-mid --target 1R --write`:

```
  Entry         ₹364.18 at 10:00 AM (bar 8)
  Stop          ₹358.30  opening-range midpoint: (₹362.18 + ₹354.47) / 2 = ₹358.325, rounded down to the 0.05 tick
  Target        ₹370.10  1R (one times the risk)
  Risk a share  ₹5.88 (1.61% of the entry)
  Reward:risk   1.01
  Flat by       15:15 IST, win or lose: no overnight hold (intraday / MIS)
```

The default 2R target is 364.18 + 2 x 5.88 = 375.94, up to the tick: 375.95.

## Rules

- The stop and the target are set before the entry, never after.
- Never move a stop further from the entry once the trade is on.
- Plain numbers only. It never prints a P&L or a return.
- Long side only. v2 plans longs only.

## What it never does

It never places an order, never sizes a position, never widens a stop to make
a plan pass, and never calls a stop a guarantee.

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
