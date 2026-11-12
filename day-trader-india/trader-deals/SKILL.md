---
name: trader-deals
description: >-
  Big-Money Tracker. Reads NSE's daily bulk deals (one client trading more
  than 0.5% of a company's shares in a day) and block deals (single trades
  of at least Rs 10 crore in the block window), which NSE publishes with the
  buyer's and seller's names after the close. Alerts once per new deal,
  flags deals in stocks you watch or hold and deals by the funds, promoters
  or investors you follow (trader/deals-watch.json). Replaces the
  US Congress-trades tracker: India has no such disclosure for politicians, and
  this is the public record of who moved big money. Use when the user says
  "who's buying", "bulk deals", "block deals", "did any fund buy X",
  "track this investor", "promoter selling", or after the close.
argument-hint: "[--symbols ...] [--client NAME] [--follow] [--min-value CRORE]"
---

# trader-deals

Every evening NSE lists the day's bulk and block deals by name. This skill
reads those lists so you see, the same evening, which fund bought how much of
what, and which promoter sold. It is fast, not early: by the next open the
deal is history. It is public information, not inside information. Say both,
every time.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/deals.py"                            # today's bulk and block deals, new ones only
python3 "${CLAUDE_SKILL_DIR}/deals.py" --symbols RELIANCE TCS
python3 "${CLAUDE_SKILL_DIR}/deals.py" --client "mutual fund" --side buy
python3 "${CLAUDE_SKILL_DIR}/deals.py" --follow                   # the clients in trader/deals-watch.json
python3 "${CLAUDE_SKILL_DIR}/deals.py" --min-value 50 --all        # Rs 50 crore and up, seen ones too
```

## What it reads and writes

| file | what |
| --- | --- |
| NSE `bulk.csv` and `block.csv` (nsearchives.nseindia.com) | the day's deals; NSE sometimes blocks scripts: then save them from the website and use `--offline DIR` |
| `trader/deals-watch.json` | `{"clients": ["part of a name"], "symbols": ["RELIANCE"]}` |
| watchlist, plan, portfolio | your symbols, flagged YOUR STOCK |
| `trader/state/deals.json` | what was shown (60 days), so each deal shows once |

## How to read a deal

- **Every buy had a seller.** A fund buying 1% means someone sold 1%.
- **One day, one party.** A bulk buy can be an arbitrage or a market maker,
  out again tomorrow. Look for the same name over days.
- **Promoter selling** (a block deal by the promoter group) and **promoter
  pledges** (in `/trader-news`) matter more than one fund's trade.
- **Block deals** happen in two short windows (one before the open, one in the
  afternoon) at a price close to the market price; the price is
  agreed between two parties, so it says little about direction.

## Steps

1. Run it after 6 PM IST on a trading day (the lists update after the close).
2. Read your stocks and followed clients first, then the biggest deals.
3. Never present a deal as a reason to trade the next morning.

## Example: the demo (fictional names)

```
2026-10-19 BULK  DEMO         BUY  12,50,000 shares at ₹364.55 = ₹45.57 cr  EXAMPLE CAPITAL FUND  [YOUR STOCK]
2026-10-19 BLOCK SOME-AUTO    SELL 20,00,000 shares at ₹2,150.00 = ₹430.00 cr  PROMOTER HOLDINGS PRIVATE LIMITED
```

## Rules

- Quote the exchange's data: names, quantities and prices as NSE published them.
- Indian digit grouping for quantities (12,50,000), crore and lakh for values.
- Not a tip, not inside information, not financial advice.

## What it never does

It never places an order, never guesses why a party traded, and never
follows or names private individuals the user did not ask about.

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
