---
name: trader-alerts
description: >-
  Price Alerts and the NSE clock. Rings when a price, your stop or your
  target hits, when a stock moves a set percent from yesterday's close, at
  the 9:15 IST opening bell, and at your flat-by time (15:15 IST, before the
  broker's intraday square-off), each once. Knows NSE's trading holidays.
  Reads free delayed Yahoo quotes (.NS) and writes trader/prices.json,
  including yesterday's close for trader-risk's circuit check. Use when the
  user says "alert me", "tell me if it hits", "watch my stop", "is the
  market open", "when does NSE open", "remind me to close", or after
  /trader-exit writes a plan.
argument-hint: "[clock|quote|add|check|list|reset]"
---

# trader-alerts

Alerts are the part of the pack that watches while you do something else.
They ring, once, and tell you what to do next. They never trade: an alert at
your target is a reminder to close, not an order.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                   # is NSE open? next open (IST)
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote RELIANCE INFY --write
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --from-plan         # stop, target and flat-by from trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol INFY --pct 3
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --opening-bell
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                   # rings what hit, once
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/alerts.json` | the rules (`alerts.example.json` in this folder shows each kind) |
| `trader/plan.json` | for `add --from-plan` |
| `trader/config.json` | `exchange` (NSE / BSE) and `extra_holidays` |
| `trader/prices.json` | the quotes, with yesterday's close |
| `trader/state/alerts.json` | what rang, so each alert rings once |

## The clock

NSE's normal session is 9:15 to 15:30 IST, Monday to Friday, closed on NSE
trading holidays (the 2026 list is built in; add next year's with
`"extra_holidays"`). India has no daylight saving: 9:15 IST is 03:45 UTC all
year. The pre-open call auction (9:00 to 9:08) is not "open". Muhurat
trading on Diwali is not modelled.

## Steps

1. After `/trader-exit`, run `add --from-plan`: a stop alert, a target alert
   and a 15:15 flat-by alert, for that day only.
2. Claude can run `alerts.py check` on a `/loop` every few minutes while the
   trade is open. Read each ring to the user with its next step.
3. At the target or the flat-by time, the next step is `/trader-broker
   flatten`, then trader-risk and the user's yes. Never send it on your own.

## Example: the demo

```
ALERT Flat by close: it is 15:15 IST (set for 15:15), the market closes at 15:30. If DEMO is still open,
close it: trader-broker flatten --symbol DEMO builds the sell ticket, then trader-risk and your yes. Your
broker squares off intraday (MIS) positions itself around 15:20 and charges for it.
```

## Rules

- Quotes are free, delayed and unofficial: for alerts, never for timing an order.
- Each alert rings once; a re-armed one rings again only after the price crosses back.

## What it never does

It never places, changes or cancels an order.

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
