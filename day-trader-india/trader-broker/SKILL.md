---
name: trader-broker
description: >-
  Order Executor. Shows each order trader-risk passed as a plain-English
  ticket and records your yes, one order at a time. Paper trading by
  default: nothing is sent anywhere, the trade is only recorded. Live, with
  Zerodha, it lists the exact place_order calls for the Kite MCP connector
  (the entry, then a SELL SL-M stop-loss) and Claude's own Allow once / Deny
  card asks again; other brokers (Upstox, Dhan, Angel One...) get the order
  details for their own connector. Builds the flatten ticket that closes a
  day trade by 15:15 IST, before the broker's MIS square-off. Use when the
  user says "place it", "buy it", "send the order", "go", "flatten",
  "square off", "close my position", or after /trader-risk passes an order.
argument-hint: "[show|approve|decline|result|fill|flatten|log]"
---

# trader-broker

The broker skill is where a trade becomes real, so it is the slowest part of
the pack on purpose. It shows one ticket, waits for an explicit yes for that
one order, and records everything. In paper mode, the default, no broker is
ever called.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                      # every order, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status placed --broker-id PAPER --filled-qty 159 --filled-price 364.20
python3 "${CLAUDE_SKILL_DIR}/ticket.py" flatten --symbol DEMO     # a sell ticket to be flat by 15:15 IST
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

## Connecting Zerodha (live only)

Zerodha runs a hosted Kite MCP server. Add it in Claude (Customize >
Connectors), or in the Claude Desktop config (`claude_desktop_config.example.json`
in this folder), and log in on Kite's own page when it asks. No API key, no
password and no TOTP ever goes in the chat. Set its order tools (place_order,
modify_order, cancel_order) to "Needs approval", never "Always allow".

## Why the target is an alert, not an order

Indian brokers no longer offer bracket orders on equities. A stop-loss order
and a target order resting on the same intraday position do NOT cancel each
other: when one fills, the other stays and can open a short. So, live, only
the entry and then its SL-M stop go to the broker. trader-alerts rings at the
target and `ticket.py flatten` closes the trade. `"target_order": "limit"`
in the config sends the target too, and then cancelling the leftover leg the
moment one fills is on you.

## Steps

1. Run `ticket.py show`. Only a READY ticket can be approved: trader-risk
   passed THIS exact order today and nobody has decided on it yet.
2. Show the ticket and ask: reply "yes" to place this one order, or "no".
3. Record the reply word for word with `approve`. It refuses "ok", "sure",
   "haan", "yes to all", or a yes that names another stock or amount.
4. Paper: record `result --status placed --broker-id PAPER` with the fill.
   Live: make the Kite calls exactly as shown (the stop only after the entry
   has filled), each behind Claude's Allow once card, then record the result.
5. Before 15:15 IST, if the trade is still open: `flatten`, cancel the open
   SL-M first, then trader-risk and a new yes for the sell.

## Example: the demo, paper

```
ORDER 1 of 1, PAPER (simulated, nothing is sent to a broker), Zerodha Kite
  BUY 159 DEMO on NSE, intraday (MIS), market, good for today
  stop-loss 358.30
  target 370.10
  max loss about ₹934.92 if the stop fills at 358.30, plus about ₹60.80 of charges
  READY: trader-risk PASS, waiting for your yes
  Reply "yes" to paper trade this one order, or "no" to skip it.
```

## Rules

- One order, one yes. Never a batch.
- Never place an order trader-risk did not pass today, and never edit one after.
- Never run this from a background watch or a loop: nobody is there to say yes.

## What it never does

It never logs in for the user, never stores credentials, never sets a tool
to "Always allow", and never sends the target and the stop together unless
the user turned that on.

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
