---
name: trader-timemachine
description: >-
  Time Machine. Replays a planned NSE day trade before you risk a rupee:
  10,000 simulated runs of the rest of the session from your entry, each
  5-minute bar drawn from the stock's own bars at that time of day over its
  last ~60 sessions, plus the same rule re-run on every one of those real
  sessions. Says how often the target came first, the stop came first, or
  neither by your flat-by time (15:15 IST), with a verdict line and an ASCII
  fan chart. Same plan and seed, same numbers. Use when the user says
  "replay this trade", "what are the odds", "backtest this", "simulate it",
  "time machine", or after /trader-exit and before /trader-budget.
argument-hint: "[run|chart] [--seed N] [--until HH:MM]"
---

# trader-timemachine

Before a rupee is at risk, the time machine runs the rest of the day ten
thousand times. Each replay walks forward from the entry one 5-minute bar at
a time, every bar borrowed whole from the same stock's past sessions at the
same time of day. Then it does the honest second check: the plan's own rule,
run on every one of those real past sessions. Day trading loses most people
money; the odds here are a reality check, not a promise.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run                 # trader/plan.json, 10,000 replays, seed 19
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --write         # also trader/timemachine.json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --until 15:30   # to the close instead of flat_by
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" chart               # ASCII fan chart
```

## How it works

1. One request: 60 days of 5-minute bars (`SYMBOL.NS`). Only FULL NSE sessions
   before the plan's date count: 75 bars, 9:15 to 15:30 IST. Short days and
   holidays drop out on their own.
2. The pool: for each bar slot, every past session's bar as ratios to the
   previous close. A replay picks a slot within two bars of the same time,
   one past bar from it, and scales it to the current price.
3. The stop is checked before the target in every bar: a bar touching both
   counts as the stop.
4. A replay ends at `--until`, which defaults to the plan's `flat_by` (15:15),
   because brokers square off intraday positions around 15:20.
5. History: the opening-range rule, stop and target R re-run on every past
   session, with stops and targets on NSE ticks like trader-exit's.

## The verdict

The share of replays that hit the target first among those that hit a side,
against the share that breaks even at the target's R (50 % at 1R, 33 % at 2R).
A target rounded up to the tick is still "1R". Under 5 points: close to a
coin flip / break-even; 5 to 15: leans; 15 or more: strongly.

## Steps

1. Run it after `/trader-exit` wrote `trader/plan.json`.
2. Read back target first, stop first, neither, the history line and the verdict.
3. Say what it cannot see: results, news, a circuit limit, an F&O ban, a halt.
4. Hand off to `/trader-budget` if the user still wants the trade.

## Example: the demo

DEMO (synthetic data), entry 364.18 at 10:00 AM, stop 358.30, target 370.10, seed 19:

```
10,000 replays of the rest of the session, 10:00 AM to 3:15 PM (63 five-minute bars), seed 19.
  target first   26.5 %
  stop first     21.9 %
  neither        51.6 %   still open at 3:15 PM
History: ... on each of those 57 real sessions fired 32 times: 12 target, 16 stop, 4 neither. Average R -0.136.
Close to a coin flip: target first 26.5 % vs stop first 21.9 %.
```

Half the replays are still open at 15:15: the price at the flat-by time
decides those, and the history leans the other way. That is the point of
looking first.

## Rules

- A simulation, not a prediction. Say so every time.
- 5-minute bars only, and at least 20 full sessions, or it refuses.
- Never call a lean a recommendation.

## What it never does

It never places an order, never sizes a trade, and never changes the plan.

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
