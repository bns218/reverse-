---
name: trader-budget
description: >-
  Budget Manager for Indian intraday trades. Sizes every position to your
  budget and your max loss per trade in rupees, counting the real round-trip
  charges (brokerage, STT, exchange transaction charge, SEBI fee, stamp duty,
  GST) inside that max loss, in whole shares. Optional MIS intraday leverage
  (up to 5x, SEBI's peak-margin floor) only when you allow margin. Writes one
  proposed order (an MIS entry with its stop-loss and target) to
  trader/orders.json for trader-risk and trader-broker. Use when the user
  says "how many shares", "size this trade", "what can I afford", "position
  size", "how much do I lose at the stop", "what are the charges", or after
  /trader-exit and /trader-timemachine, before /trader-risk.
argument-hint: "[--budget N] [--limit [PRICE]] [--write]"
---

# trader-budget

The budget manager turns a plan into a number of shares. It starts from the
most you are willing to lose if the stop fills, takes off what the trade
costs in charges, and checks the result against your position cap, your
largest order and the cash you have. The smallest answer wins. Day trading
loses most people money; small, fixed losses are what keep it survivable.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                        # trader/plan.json + trader/config.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --write                # write trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit                # a limit order at the plan's entry
python3 "${CLAUDE_SKILL_DIR}/size.py" --budget 200000 --json
python3 "${CLAUDE_SKILL_DIR}/size.py" --weights RELIANCE=30,HDFCBANK=25,INFY=20 --budget 100000   # split a budget
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | from trader-exit: entry, stop, target, flat by |
| `trader/config.json` | copy `config.example.json` from this folder: budget, limits in rupees, charges |
| `trader/prices.json` | a fresh (under 15 minutes) higher price sizes the risk from there |
| `trader/portfolio.json` | if it exists, its cash caps the size |
| `trader/orders.json` | with `--write`: the one proposed order |

## How many shares

- **max loss**: the most shares whose loss at the stop PLUS the round trip's
  charges fits in `max_loss_per_trade_inr` (₹1,000 in the example config).
- **position cap**: budget x `max_position_pct` / entry.
- **max order**: `max_order_inr` / entry.
- **cash**: budget minus the cash buffer, / entry. With `"allow_margin": true`
  and `"intraday_leverage": N` (1 to 5) an MIS order needs only value / N of
  margin. Leverage never raises the max loss: that limit still binds first.

Zero shares, a reward:risk under your minimum, or an order under
`min_order_inr` is a plain refusal: no order is written.

## Charges (estimates; brokers and exchanges revise them)

Intraday equity, per round trip: brokerage 0.03% or ₹20 an order, whichever
is lower; STT 0.025% on the sell side; NSE transaction charge 0.00297%;
SEBI fee ₹10 a crore; stamp duty 0.003% on the buy side; GST 18% on
brokerage + exchange + SEBI. Override any rate with `"charges"` in the
config (a zero-brokerage plan: `"brokerage_pct": 0`), or turn the maths off
with `"include_charges": false`.

## Steps

1. Run `size.py` after `/trader-exit` (and `/trader-timemachine`).
2. Read back the limits, which one binds, the shares, the cost, the loss at
   the stop with and without charges, and the margin needed.
3. If it refuses, say why and the fix (a closer stop, a smaller order). Never
   raise a limit for the user.
4. With `--write`, hand off to `/trader-risk`.

## Example: the demo

₹1,00,000 budget, 10% cash buffer, ₹1,000 max loss, DEMO entry 364.18, stop 358.30:

```
  max loss      ₹1,000 max loss / (5.88 risk a share + charges)            159 shares  <- binds
Size: 159 shares of DEMO = ₹57,904.62 at 364.18. Max loss at the stop: 159 x 5.88 = ₹934.92.
Charges if it stops out (estimate): brokerage ₹34.46, STT ₹14.24, exchange ₹3.41, SEBI ₹0.11, stamp duty ₹1.74, GST ₹6.84 = ₹60.80. Loss at the stop with charges: ₹995.72.
  buy 159 DEMO on NSE, MIS, market, day, target 370.10, stop-loss 358.30
```

Without the charges it would have said 170 shares, and a full stop-out would
have cost more than the ₹1,000 you set.

## Rules

- Whole shares only: Indian exchanges have no fractional shares.
- Every number in rupees; the charges are estimates and are labelled so.
- Never size a trade without a stop.

## What it never does

It never places an order, never moves the stop to fit more shares, and never
turns leverage on by itself.

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
