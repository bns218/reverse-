---
name: trader-analyst
description: >-
  Earnings Analyst for NSE and BSE companies. Reads a company's reported
  quarterly numbers (revenue, gross, operating and net margins, net profit,
  diluted EPS) in rupees crore, by Indian fiscal quarter (Q2 FY27 = July to
  September 2026), and sums up what changed against the same quarter a year
  earlier and the quarter before, with trailing-four-quarter totals. Free
  Yahoo Finance fundamentals, no key; points to the results filing on
  nseindia.com for the details. Use when the user says "how were the
  results", "earnings", "quarterly results", "Q2 numbers", "is revenue
  growing", "compare TCS and Infosys", or before trading around a results
  announcement.
argument-hint: "SYMBOL [SYMBOL ...] [--quarters N] [--metrics FILE]"
---

# trader-analyst

The analyst reads the numbers a company reported and says what changed, in
plain words. Indian listed companies file results every quarter under SEBI's
LODR rules (within 45 days of a quarter's end, 60 for the year's last
quarter), so every row is a reported quarter.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE
python3 "${CLAUDE_SKILL_DIR}/facts.py" TCS INFY --quarters 8
python3 "${CLAUDE_SKILL_DIR}/facts.py" HDFCBANK --json
python3 "${CLAUDE_SKILL_DIR}/facts.py" RELIANCE TCS --metrics trader/metrics.json
```

## Where the numbers come from

Yahoo Finance's fundamentals time series for `SYMBOL.NS` (free, unofficial):
quarterly total revenue, gross profit, operating income, net income and
diluted EPS, in rupees. Yahoo can lag the exchange filing by days, can show
consolidated where you expect standalone, and banks, NBFCs and insurers
report revenue differently, so their margins can be blank or odd. For the
filing itself (standalone and consolidated, notes, the auditor's remarks):
nseindia.com > Corporate Filings > Financial Results, or `/trader-news`.

## Steps

1. Run `facts.py SYMBOL` and read the latest quarter's line under "What changed".
2. Compare with a year earlier first: many businesses are seasonal.
3. Flag other income: when net profit is above operating profit, say the
   quarter includes gains outside the business and point to the filing.
4. For a trade, say whether results are due this week (`/trader-news`).

## Example: the demo (a fictional company)

```
quarter end fiscal       revenue  rev yoy   gross    oper     net   net prof  EPS dil EPS yoy
2026-09-30  Q2 FY27        5,420   +13.2%   40.6%   15.9%   10.9%        590    11.80  +22.9%
Last 4 quarters: revenue ₹20,720 cr, net profit ₹2,170 cr, diluted EPS ₹43.40.
```

## Rules

- Numbers only: never say whether a stock is a buy.
- Always rupees crore for big numbers (1 crore = 10 million).
- Say when Yahoo's numbers are missing or stale, and send the user to the filing.

## What it never does

It never estimates future earnings, never prints a target price, and never
trades.

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
