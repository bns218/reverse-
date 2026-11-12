#!/usr/bin/env python3
"""Big-money tracker for trader-deals (India). Standard library only.

NSE publishes every BULK deal (one client trading more than 0.5% of a
company's shares in a day) and every BLOCK deal (a single trade of at least
Rs 10 crore in the special block-deal window) after the close, by name: the
fund, the promoter, the investor. This tool reads those lists, alerts once
per new deal, and flags deals in the stocks you watch or hold and deals by
the investors you follow.

    python3 deals.py                                   # today's bulk and block deals
    python3 deals.py --symbols RELIANCE TCS            # only these stocks
    python3 deals.py --client "example capital"        # only this buyer or seller (any part of the name)
    python3 deals.py --follow                          # the investors in trader/deals-watch.json
    python3 deals.py --side buy --min-value 50         # buys of Rs 50 crore or more
    python3 deals.py --all                             # seen deals too
    python3 deals.py --offline DIR                     # DIR/bulk.csv and DIR/block.csv

Sources (NSE's public archive CSVs, refreshed each trading day after the close):
  https://nsearchives.nseindia.com/content/equities/bulk.csv
  https://nsearchives.nseindia.com/content/equities/block.csv
Columns: Date, Symbol, Security Name, Client Name, Buy/Sell, Quantity Traded,
Trade Price / Wght. Avg. Price, Remarks. They are matched by name, so a
reordered or renamed column still reads. NSE sometimes refuses scripted
downloads: save the CSVs from nseindia.com (Market Data > Bulk & Block Deals)
into a folder and use --offline.

trader/deals-watch.json (optional): {"clients": ["part of a name", ...],
"symbols": ["RELIANCE", ...]}. Your watchlist, plan and portfolio symbols are
watched too. State: trader/state/deals.json remembers what was shown (60 days).

It is fast, not early: a bulk deal is public the evening it happens, so it
is history by the next open. It is public information, not inside
information. A deal is one trade by one party, not a recommendation: the
same fund can be on the other side tomorrow, and a "buy" by one client is
always a "sell" by someone else.
"""

import argparse
import csv
import datetime as _dt
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

URLS = {"bulk": "https://nsearchives.nseindia.com/content/equities/bulk.csv",
        "block": "https://nsearchives.nseindia.com/content/equities/block.csv"}
UA = "Mozilla/5.0 (compatible; day-trader-skill/2.0; +https://github.com/Jakeschincariol/day-trader-skill)"
CRORE = 1e7
KEEP_DAYS = 60
COLUMNS = {   # our name -> header words that identify it (lower case, any order)
    "date": ("date",),
    "symbol": ("symbol",),
    "name": ("security name", "security"),
    "client": ("client name", "client"),
    "side": ("buy/sell", "buy / sell", "buy sell", "trade type"),
    "qty": ("quantity traded", "quantity", "qty"),
    "price": ("trade price", "wght. avg", "price"),
    "remarks": ("remarks",),
}


class DealsError(Exception):
    pass


def _num(text):
    t = re.sub(r"[^\d.\-]", "", str(text or ""))
    try:
        return float(t) if t not in ("", "-", ".") else None
    except ValueError:
        return None


def _date(text):
    t = str(text or "").strip()
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return _dt.datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def _match_columns(header):
    """{our name: index} from a header row, by the words in each column name."""
    norm = [" ".join(h.replace("﻿", "").strip().lower().split()) for h in header]
    out = {}
    for key, words in COLUMNS.items():
        for i, h in enumerate(norm):
            if i in out.values():
                continue
            if any(h == w or h.startswith(w) or w in h for w in words):
                out[key] = i
                break
    return out


def parse_deals(text, kind):
    """bulk.csv / block.csv text -> deals. Raises DealsError when it is not that CSV."""
    rows = [r for r in csv.reader(io.StringIO(text.replace("\r", ""))) if any(c.strip() for c in r)]
    if not rows:
        return []
    col = _match_columns(rows[0])
    missing = [k for k in ("symbol", "client", "side", "qty") if k not in col]
    if missing:
        raise DealsError("the %s deals file has no %s column (got: %s). NSE may have sent a web page instead "
                         "of the CSV" % (kind, ", ".join(missing), ",".join(rows[0])[:100]))
    out = []
    for r in rows[1:]:
        def at(k):
            i = col.get(k)
            return r[i].strip() if i is not None and i < len(r) else ""
        side = at("side").upper()
        side = "buy" if side.startswith("B") else "sell" if side.startswith("S") else side.lower()
        qty, price = _num(at("qty")), _num(at("price"))
        sym = at("symbol").upper()
        if not sym or qty is None:
            continue
        d = _date(at("date"))
        out.append({"kind": kind, "date": d.isoformat() if d else at("date"), "symbol": sym, "name": at("name"),
                    "client": " ".join(at("client").split()), "side": side, "qty": int(qty),
                    "price": price, "value": round(qty * price, 2) if price is not None else None,
                    "remarks": at("remarks") if at("remarks") not in ("-", "") else ""})
    return out


def fingerprint(d):
    key = "|".join(str(d.get(k)) for k in ("kind", "date", "symbol", "client", "side", "qty", "price"))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def fetch(kind, offline=None):
    if offline:
        p = os.path.join(offline, "%s.csv" % kind)
        if not os.path.exists(p):
            raise DealsError("offline: no %s" % p)
        with open(p, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    req = urllib.request.Request(URLS[kind], headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise DealsError("NSE answered HTTP %d for the %s deals" % (e.code, kind))
    except (urllib.error.URLError, OSError) as e:
        raise DealsError("could not reach NSE for the %s deals: %s" % (kind, getattr(e, "reason", e)))


def load_json(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def your_symbols(portfolio, watchlist, plan, watch):
    out = set(s.upper() for s in (watch or {}).get("symbols", []))
    for h in (load_json(watchlist) or {}).get("hits", []):
        if h.get("symbol"):
            out.add(h["symbol"].upper())
    p = load_json(plan) or {}
    if p.get("symbol"):
        out.add(p["symbol"].upper())
    for pos in (load_json(portfolio) or {}).get("positions", []):
        s = pos.get("ticker") or pos.get("symbol")
        if s:
            out.add(s.upper())
    return out


def client_match(client, names):
    c = client.lower()
    return [n for n in names if n and n.lower() in c]


def select(deals, symbols=None, clients=None, side=None, min_value_cr=None):
    out = []
    for d in deals:
        if symbols and d["symbol"] not in symbols:
            continue
        if clients and not client_match(d["client"], clients):
            continue
        if side and d["side"] != side:
            continue
        if min_value_cr and (d["value"] is None or d["value"] < min_value_cr * CRORE - 0.5):
            continue
        out.append(d)
    return out


LAKH = 1e5


def indian(n):
    """1250000 -> "12,50,000": the lakh / crore grouping NSE prints."""
    s = str(int(round(abs(n))))
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    return ("-" if n < 0 else "") + (head + "," + tail if head else tail)


def money(v):
    if v is None:
        return "n/a"
    if abs(v) >= CRORE:
        return "₹{:,.2f} cr".format(v / CRORE)
    return "₹{:,.2f} lakh".format(v / LAKH)


def render(deals, yours, followed, notes):
    lines = []
    if not deals:
        lines.append("No new deals.")
    for d in deals:
        flags = []
        if d["symbol"] in yours:
            flags.append("YOUR STOCK")
        hits = client_match(d["client"], followed)
        if hits:
            flags.append("FOLLOWED: " + ", ".join(hits))
        lines.append("%s %-5s %-12s %-4s %s shares at %s = %s  %s%s" % (
            d["date"], d["kind"].upper(), d["symbol"], d["side"].upper(), indian(d["qty"]),
            "₹{:,.2f}".format(d["price"]) if d["price"] is not None else "n/a", money(d["value"]), d["client"],
            ("  [" + "; ".join(flags) + "]") if flags else ""))
    for n in notes:
        lines.append("note: " + n)
    lines.append("Public deal data from NSE, published after the close: history by the next open, not a tip. "
                 "Every buy here had a seller. Not financial advice.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="NSE bulk and block deals (trader-deals).")
    ap.add_argument("--symbols", nargs="*", help="only these stocks")
    ap.add_argument("--client", action="append", help="only deals whose client name contains this (repeatable)")
    ap.add_argument("--follow", action="store_true", help="only the clients in trader/deals-watch.json")
    ap.add_argument("--side", choices=["buy", "sell"])
    ap.add_argument("--min-value", type=float, metavar="CRORE", help="only deals worth at least this many crore")
    ap.add_argument("--kind", choices=["bulk", "block", "both"], default="both")
    ap.add_argument("--all", action="store_true", help="show deals already shown before")
    ap.add_argument("--watch", default="trader/deals-watch.json")
    ap.add_argument("--portfolio", default="trader/portfolio.json")
    ap.add_argument("--watchlist", default="trader/watchlist.json")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--state", default="trader/state/deals.json")
    ap.add_argument("--offline", metavar="DIR", help="read DIR/bulk.csv and DIR/block.csv")
    ap.add_argument("--now", help="YYYY-MM-DD, for reproducible runs")
    ap.add_argument("--dry-run", action="store_true", help="do not update the state file")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    today = _dt.date.fromisoformat(a.now[:10]) if a.now else _dt.date.today()
    watch = load_json(a.watch) or {}
    followed = [str(c) for c in watch.get("clients", [])]
    yours = your_symbols(a.portfolio, a.watchlist, a.plan, watch)
    deals, notes = [], []
    for kind in (("bulk", "block") if a.kind == "both" else (a.kind,)):
        try:
            deals += parse_deals(fetch(kind, a.offline), kind)
        except DealsError as e:
            notes.append(str(e))
    if not deals and notes and len(notes) == (2 if a.kind == "both" else 1):
        for n in notes:
            print("deals.py: %s" % n, file=sys.stderr)
        print("deals.py: save the CSVs from nseindia.com (Market Data > Bulk & Block Deals) and use --offline DIR",
              file=sys.stderr)
        return 2
    clients = list(a.client or [])
    if a.follow:
        if not followed:
            print("deals.py: --follow needs \"clients\" in %s" % a.watch, file=sys.stderr)
            return 2
        clients += followed
    syms = {s.upper() for s in a.symbols} if a.symbols else None
    picked = select(deals, syms, clients, a.side, a.min_value)
    state = load_json(a.state) or {}
    seen = state.setdefault("seen", {})
    shown = [d for d in picked if a.all or fingerprint(d) not in seen]
    shown.sort(key=lambda d: (d["date"], d["symbol"] in yours, d["value"] or 0), reverse=True)
    if a.json:
        print(json.dumps({"deals": [dict(d, yours=d["symbol"] in yours,
                                         followed=client_match(d["client"], followed),
                                         new=fingerprint(d) not in seen) for d in shown],
                          "notes": notes}, indent=2))
    else:
        sys.stdout.write(render(shown, yours, followed, notes))
    if not a.dry_run:
        stamp = today.isoformat()
        for d in picked:
            seen.setdefault(fingerprint(d), stamp)
        cutoff = (today - _dt.timedelta(days=KEEP_DAYS)).isoformat()
        state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
        d = os.path.dirname(a.state)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.state, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
    return 0 if shown else 1


if __name__ == "__main__":
    sys.exit(main())
