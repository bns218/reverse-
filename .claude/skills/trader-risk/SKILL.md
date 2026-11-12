---
name: trader-risk
description: >-
  Risk Manager. Checks every proposed order against your limits before it can
  reach the broker, and stops anything over them: PASS or BLOCK with the
  reasons. For an Indian intraday trade: whole shares on NSE or BSE, an MIS /
  CNC product, a stop is required, the loss at the stop plus charges must fit
  max_loss_per_trade_inr, reward:risk must meet your minimum, the day's
  total risk and trade count must fit, no new entries before 09:30 or after
  14:45 IST or on NSE holidays, no entry near the upper circuit or stop under
  the lower one, no F&O, margin or shorts unless allowed. Records each
  verdict with a fingerprint so only that exact order can be placed. Use when
  the user says "check this trade", "is this within my limits", "risk check",
  or after /trader-budget, before /trader-broker.
argument-hint: "[--orders FILE] [--now \"YYYY-MM-DD HH:MM\"]"
---

# trader-risk

The risk manager is the gate. Every order trader-budget proposes goes
through it, and only a PASS can reach the broker. It checks the order as
written, against your own rules, as if everything it passed earlier in the
same batch had filled. Getting out is never blocked: an exit is only checked
for format, asset and short sales.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                          # the trader/ files; writes trader/state/risk.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --now "2026-10-19 10:00"  # pin the clock (IST)
python3 "${CLAUDE_SKILL_DIR}/check.py" --json --no-write
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders |
| `trader/config.json` | your limits (see trader-budget's `config.example.json`) |
| `trader/portfolio.json` | cash and holdings; missing = a fresh account funded with the budget |
| `trader/prices.json` | fresh prices, and yesterday's close for the circuit check |
| `trader/state/broker.json` | what was placed today |
| `trader/state/risk.json` | the verdicts and fingerprints |

## What blocks an order

- **format**: whole shares only (no notional rupee amount, no fractions); an
  exchange other than NSE or BSE; a product other than MIS, CNC or NRML; no
  extended hours (an AMO only queues for the next open); an order with a stop
  and target that is not a day order or misses a leg.
- **asset**: F&O contracts (NIFTY26OCTFUT, RELIANCE26OCT1400CE) unless
  `"allow_options": true`; anything that is not an NSE or BSE equity symbol.
- **short**: selling more than you hold, unless `"allow_short": true`.

On top, for an entry: your blocked list (put trade-for-trade, ASM / GSM and
F&O-ban stocks there), min and max order, the position cap, cash and margin
(leverage only with `"allow_margin": true`, up to 5x, MIS only), duplicates,
the daily order limit, the **circuit** check (when a price band is set:
`"price_band_pct"` or `"price_bands": {"SYMBOL": 5}`), a required stop on the
right side, the **loss** at the stop plus the plan's charges over
`max_loss_per_trade_inr`, reward:risk, the daily loss limit, trades per day,
and the **window**: 09:30 to 14:45 IST on an NSE trading day.

## Steps

1. Run `check.py` after `/trader-budget --write`.
2. Say PASS or BLOCK for each order with every reason, word for word.
3. On a BLOCK, say what would fix it. Never edit the user's limits to pass.
4. On a PASS, hand off to `/trader-broker`, which still asks for a yes.

## Example: the demo

```
PASS  #1 buy DEMO 159 shares, entry
          charges if it stops out (estimate) ₹60.80: ₹995.72 with the loss at the stop
          entry 364.18 (the plan's entry), stop 358.30, target 370.10: risk 5.88 a share
          max loss ₹934.92 (limit ₹1,000), reward:risk 1.01 (min 1)
```

At 15:00 the same order is blocked: no new entries after 14:45 IST.

## Rules

- A PASS is a rules check, not a recommendation.
- The verdict is for that exact order today: edit one share and it must be checked again.
- There is no US pattern-day-trader rule in India; the daily loss and trade limits do that job.

## What it never does

It never places an order, never changes an order to make it pass, and never
loosens a limit.

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
