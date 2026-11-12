#!/usr/bin/env python3
"""Earnings reader for trader-analyst (India: NSE / BSE). Standard library only.

Pulls a company's reported quarterly numbers and lays out what changed,
quarter by quarter: revenue, gross, operating and net margins, net profit,
diluted EPS, and growth against the same quarter a year earlier. Indian
companies file results every quarter (SEBI's LODR rules: within 45 days of a
quarter's end, 60 days for the year's last quarter), so every quarter is a
reported one; nothing is derived.

    python3 facts.py RELIANCE
    python3 facts.py TCS INFY --quarters 8
    python3 facts.py HDFCBANK --json
    python3 facts.py RELIANCE TCS INFY --metrics trader/metrics.json

Source: Yahoo Finance's fundamentals time series (free, unofficial, no key),
one request per symbol:
  https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/<SYMBOL>.NS
      ?type=quarterlyTotalRevenue,quarterlyGrossProfit,quarterlyOperatingIncome,
            quarterlyNetIncome,quarterlyDilutedEPS&period1=...&period2=...
Values are in rupees (the answer's currencyCode is checked and printed).
Banks, NBFCs and insurers report revenue differently; their margins can be
blank or odd. Yahoo can lag the exchange filing by days and can carry
consolidated numbers where you expect standalone: for the filing itself,
read the company's results announcement on nseindia.com (Corporate Filings >
Financial Results) or run /trader-news for the announcement.

--metrics FILE merges one row per symbol into a JSON file (TTM revenue and
EPS, margins, growth). Offline: --offline DIR reads timeseries-<SYMBOL>.json
from DIR. The tests use it.

Numbers only: this tool never says whether a stock is a buy.
"""

import argparse
import datetime as _dt
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; day-trader-skill/2.0; +https://github.com/Jakeschincariol/day-trader-skill)"
HOSTS = ("query2", "query1")
TS_URL = "https://%s.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/%s?%s"
TYPES = {"revenue": "quarterlyTotalRevenue", "gross_profit": "quarterlyGrossProfit",
         "operating_income": "quarterlyOperatingIncome", "net_income": "quarterlyNetIncome",
         "eps_diluted": "quarterlyDilutedEPS"}
SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
CRORE = 1e7


class FactsError(Exception):
    pass


# ---------------------------------------------------------------- fetching

def yahoo_symbol(sym, exchange="NSE"):
    s = sym.strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + SUFFIX.get(str(exchange).upper(), ".NS")


def bare(sym):
    s = sym.strip().upper()
    return s[:-3] if s.endswith(".NS") or s.endswith(".BO") else s


def ts_query(now=None, years=3):
    now = now or _dt.datetime.now(_dt.timezone.utc)
    p2 = int(now.timestamp())
    p1 = p2 - int(years * 366 * 86400)
    return urllib.parse.urlencode({"type": ",".join(TYPES.values()), "period1": p1, "period2": p2,
                                   "merge": "false", "padTimeSeries": "true"}, safe=",")


class Fetcher(object):
    def __init__(self, offline=None, pause=0.5, exchange="NSE"):
        self.offline, self.pause, self.exchange, self._last = offline, pause, exchange, 0.0

    def timeseries(self, sym):
        if self.offline:
            path = os.path.join(self.offline, "timeseries-%s.json" % bare(sym))
            if not os.path.exists(path):
                path += ".gz"
            if not os.path.exists(path):
                raise FactsError("offline: no timeseries-%s.json in %s" % (bare(sym), self.offline))
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        last = "no answer"
        for host in HOSTS:
            gap = time.time() - self._last
            if gap < self.pause:
                time.sleep(self.pause - gap)
            self._last = time.time()
            url = TS_URL % (host, urllib.parse.quote(yahoo_symbol(sym, self.exchange), safe=".-"), ts_query())
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as e:
                last = "HTTP %d" % e.code
                if e.code != 429 and e.code < 500:
                    break
            except (urllib.error.URLError, OSError, ValueError) as e:
                last = str(getattr(e, "reason", e))
        raise FactsError("Yahoo's fundamentals for %s did not come back (%s)" % (sym, last))


# ---------------------------------------------------------------- facts

def _date(s):
    return _dt.date.fromisoformat(s)


def series_from(doc):
    """Yahoo timeseries JSON -> ({key: {end: value}}, currency). Missing points (null) are skipped."""
    try:
        results = doc["timeseries"]["result"] or []
    except (KeyError, TypeError):
        raise FactsError("Yahoo's answer is not the fundamentals time series this tool knows")
    rev_types = {v: k for k, v in TYPES.items()}
    out = {k: {} for k in TYPES}
    currencies = set()
    for res in results:
        typ = ((res.get("meta") or {}).get("type") or [None])[0]
        key = rev_types.get(typ)
        if not key:
            continue
        for p in res.get(typ) or []:
            if not p or not p.get("asOfDate"):
                continue
            if p.get("periodType") not in (None, "3M"):
                continue
            v = (p.get("reportedValue") or {}).get("raw")
            if v is None:
                continue
            out[key][p["asOfDate"]] = float(v)
            if p.get("currencyCode"):
                currencies.add(p["currencyCode"])
    return out, (sorted(currencies)[0] if len(currencies) == 1 else ("/".join(sorted(currencies)) or None))


def _yoy(series_, end, slack=20):
    """The value for the same quarter a year earlier, if there is one."""
    target = _date(end) - _dt.timedelta(days=365)
    best = None
    for e, v in series_.items():
        d = abs((_date(e) - target).days)
        if d <= slack and (best is None or d < best[0]):
            best = (d, v)
    return best[1] if best else None


def pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return round((a / b - 1) * 100 if b > 0 else (a - b) / abs(b) * 100, 1)


def margin(part, whole):
    if part is None or not whole:
        return None
    return round(part / whole * 100, 1)


def fiscal_label(end):
    """India's fiscal year runs April to March: the quarter ending 2026-09-30 is Q2 FY27."""
    d = _date(end)
    fy = d.year + 1 if d.month >= 4 else d.year
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
    return ("Q%d FY%02d" % (q, fy % 100)) if q else ("FY%02d" % (fy % 100))


def analyse(doc, quarters=6, name=None):
    """Every number in the report, as a dict."""
    s, currency = series_from(doc)
    rev = s["revenue"]
    if not rev and not s["net_income"]:
        raise FactsError("no quarterly revenue or net profit in Yahoo's answer (a new listing, or not covered)")
    ends = sorted(set(rev) | set(s["net_income"]), reverse=True)[:quarters]
    rows = []
    for end in ends:
        r, gp = rev.get(end), s["gross_profit"].get(end)
        oi, ni, eps = s["operating_income"].get(end), s["net_income"].get(end), s["eps_diluted"].get(end)
        rows.append({
            "end": end, "fiscal": fiscal_label(end),
            "revenue": r, "gross_profit": gp, "operating_income": oi, "net_income": ni,
            "eps_diluted": round(eps, 2) if eps is not None else None,
            "gross_margin": margin(gp, r), "operating_margin": margin(oi, r), "net_margin": margin(ni, r),
            "revenue_yoy": pct(r, _yoy(rev, end)),
            "net_income_yoy": pct(ni, _yoy(s["net_income"], end)),
            "eps_yoy": pct(eps, _yoy(s["eps_diluted"], end)),
        })
    ttm = {}
    for key in ("revenue", "net_income", "eps_diluted"):
        last4 = sorted(s[key])[-4:]
        if len(last4) == 4 and (_date(last4[-1]) - _date(last4[0])).days < 300:
            ttm[key] = sum(s[key][e] for e in last4)
    if "eps_diluted" in ttm:
        ttm["eps_diluted"] = round(ttm["eps_diluted"], 2)
    return {"entity": name, "currency": currency, "rows": rows, "ttm": ttm}


def money(v, currency="INR"):
    """Rupees in crore (1 crore = 10 million), the way Indian results are read."""
    if v is None:
        return "n/a"
    if currency not in (None, "INR"):
        return "%s %.1fM" % (currency, v / 1e6)
    return "₹{:,.0f} cr".format(v / CRORE) if abs(v) >= 100 * CRORE else "₹{:,.2f} cr".format(v / CRORE)


def changes(result):
    """Plain sentences: what changed in the latest quarter."""
    rows = result["rows"]
    if not rows:
        return []
    cur, prev = rows[0], (rows[1] if len(rows) > 1 else None)
    c = result.get("currency")
    out = []
    line = "%s (quarter ending %s): revenue %s" % (cur["fiscal"], cur["end"], money(cur["revenue"], c))
    if cur["revenue_yoy"] is not None:
        line += " (%+.1f%% vs a year earlier)" % cur["revenue_yoy"]
    line += ", net profit %s" % money(cur["net_income"], c)
    if cur["net_income_yoy"] is not None:
        line += " (%+.1f%%)" % cur["net_income_yoy"]
    if cur["eps_diluted"] is not None:
        line += ", diluted EPS ₹%.2f" % cur["eps_diluted"] if c in (None, "INR") else \
            ", diluted EPS %.2f" % cur["eps_diluted"]
        if cur["eps_yoy"] is not None:
            line += " (%+.1f%%)" % cur["eps_yoy"]
    out.append(line + ".")
    for key, label in (("gross_margin", "Gross margin"), ("operating_margin", "Operating margin"),
                       ("net_margin", "Net margin")):
        if cur[key] is None:
            continue
        txt = "%s %.1f%%" % (label, cur[key])
        if prev and prev[key] is not None:
            txt += " (%+.1f points vs the quarter before)" % (cur[key] - prev[key])
        out.append(txt + ".")
    if cur["net_income"] is not None and cur["operating_income"] is not None \
            and cur["net_income"] > cur["operating_income"]:
        out.append("Net profit is above operating profit: it includes other income or exceptional items "
                   "(investment gains, tax write-backs). Read the results filing before reading it as growth.")
    if prev and cur["revenue"] is not None and prev["revenue"]:
        out.append("Revenue %+.1f%% vs the quarter before (many businesses are seasonal: compare with a "
                   "year earlier first)." % pct(cur["revenue"], prev["revenue"]))
    return out


# ---------------------------------------------------------------- output

def _cr(v):
    return "-" if v is None else "{:,.0f}".format(v / CRORE)


def _p(v):
    return "-" if v is None else ("%+.1f%%" % v if v else "0.0%")


def _pm(v):
    return "-" if v is None else "%.1f%%" % v


def render(symbol, result):
    c = result.get("currency")
    unit = "₹ crore" if c in (None, "INR") else "%s (in crore units)" % c
    out = ["%s (%s). %s except EPS. Source: Yahoo Finance fundamentals (unofficial)." % (
        result["entity"] or symbol, symbol, unit[:1].upper() + unit[1:]), ""]
    out.append("%-11s %-9s %10s %8s %7s %7s %7s %10s %8s %7s" % (
        "quarter end", "fiscal", "revenue", "rev yoy", "gross", "oper", "net", "net prof", "EPS dil", "EPS yoy"))
    for r in result["rows"]:
        out.append("%-11s %-9s %10s %8s %7s %7s %7s %10s %8s %7s" % (
            r["end"], r["fiscal"], _cr(r["revenue"]), _p(r["revenue_yoy"]), _pm(r["gross_margin"]),
            _pm(r["operating_margin"]), _pm(r["net_margin"]), _cr(r["net_income"]),
            "-" if r["eps_diluted"] is None else "%.2f" % r["eps_diluted"], _p(r["eps_yoy"])))
    t = result["ttm"]
    if t:
        out.append("")
        out.append("Last 4 quarters: revenue %s, net profit %s, diluted EPS %s." % (
            money(t.get("revenue"), c) if t.get("revenue") is not None else "-",
            money(t.get("net_income"), c) if t.get("net_income") is not None else "-",
            ("₹%.2f" % t["eps_diluted"]) if t.get("eps_diluted") is not None else "-"))
    out.append("")
    out.append("What changed:")
    for line in changes(result):
        out.append("  - " + line)
    if c not in (None, "INR"):
        out.append("")
        out.append("NOTE: Yahoo reports this company in %s, not rupees." % c)
    out.append("")
    out.append("For the filing itself (standalone and consolidated, notes, auditor's remarks): nseindia.com > "
               "Corporate Filings > Financial Results for %s, or /trader-news %s." % (symbol, symbol))
    return "\n".join(out) + "\n"


def metrics_row(symbol, result):
    cur = result["rows"][0] if result["rows"] else {}
    t = result["ttm"]
    return {"ticker": symbol, "name": result["entity"], "currency": result.get("currency"),
            "period_end": cur.get("end"), "fiscal": cur.get("fiscal"),
            "revenue_ttm": t.get("revenue"), "net_income_ttm": t.get("net_income"), "eps_ttm": t.get("eps_diluted"),
            "revenue_growth_yoy": cur.get("revenue_yoy"), "eps_growth_yoy": cur.get("eps_yoy"),
            "net_income_growth_yoy": cur.get("net_income_yoy"),
            "gross_margin": cur.get("gross_margin"), "operating_margin": cur.get("operating_margin"),
            "net_margin": cur.get("net_margin"), "source": "Yahoo Finance fundamentals time series"}


def names_from_universe(path="trader/universe.txt"):
    out = {}
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                if "|" in ln and not ln.startswith("#"):
                    sym, nm = ln.strip().split("|", 1)
                    out[sym.strip().upper()] = nm.strip() or None
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Quarterly results for NSE / BSE companies (trader-analyst).")
    ap.add_argument("symbols", nargs="+", help="NSE symbols, e.g. RELIANCE TCS (or TCS.BO for BSE)")
    ap.add_argument("--quarters", type=int, default=6)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--metrics", metavar="FILE", help="merge one row per symbol into this JSON file")
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--config", default="trader/config.json")
    ap.add_argument("--universe", default="trader/universe.txt", help="SYMBOL|Name file, for company names")
    a = ap.parse_args(argv)
    cfg = {}
    if a.config and os.path.exists(a.config):
        try:
            with open(a.config, encoding="utf-8") as fh:
                cfg = json.load(fh) or {}
        except ValueError:
            cfg = {}
    names = names_from_universe(a.universe)
    fetcher = Fetcher(a.offline, exchange=str(cfg.get("exchange") or "NSE"))
    results, errors = {}, []
    for raw in a.symbols:
        sym = bare(raw)
        try:
            results[sym] = analyse(fetcher.timeseries(raw), a.quarters, names.get(sym))
        except FactsError as e:
            errors.append("%s: %s" % (sym, e))
    if a.json:
        print(json.dumps({"results": results, "errors": errors}, indent=2))
    else:
        for i, (sym, res) in enumerate(results.items()):
            if i:
                print()
            sys.stdout.write(render(sym, res))
        for e in errors:
            print("facts.py: %s" % e, file=sys.stderr)
        if results:
            print("\nNumbers only, not advice. Yahoo's data is free and unofficial: check anything that matters "
                  "against the exchange filing.")
    if a.metrics and results:
        doc = {}
        if os.path.exists(a.metrics):
            with open(a.metrics, encoding="utf-8") as fh:
                doc = json.load(fh)
        rows = {r["ticker"]: r for r in doc.get("companies", [])}
        for sym, res in results.items():
            rows[sym] = metrics_row(sym, res)
        doc = {"as_of": _dt.date.today().isoformat(), "companies": [rows[k] for k in sorted(rows)]}
        d = os.path.dirname(a.metrics)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.metrics, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
    return 0 if results and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
