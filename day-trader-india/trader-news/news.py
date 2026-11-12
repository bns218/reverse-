#!/usr/bin/env python3
"""News monitor for trader-news (India: NSE / BSE). Standard library only.

Watches headlines and exchange announcements for the stocks you watch or hold
and prints only what is new since the last check, newest first, with how far
each stock has moved today and a flag on anything that touches your symbols.

    python3 news.py                                  # watchlist + plan + portfolio symbols
    python3 news.py --tickers RELIANCE TCS INFY
    python3 news.py --tickers RELIANCE --all --hours 72  # everything in the last 3 days, seen or not
    python3 news.py --no-filings                     # headlines only
    python3 news.py --no-google                      # skip Google News
    python3 news.py --no-moves                       # skip the price line per symbol

Your symbols, when --tickers is not given: every hit in trader/watchlist.json
(trader-scanner), the symbol in trader/plan.json (trader-exit) and the
positions in trader/portfolio.json. Company names come from those files and
from trader/universe.txt (SYMBOL|Name, written by `scan.py universe`); a name
makes the Google News search and the announcement match much better.

Sources:
  - Yahoo Finance headline RSS, one request per symbol:
    https://feeds.finance.yahoo.com/rss/2.0/headline?s=<SYMBOL>.NS&region=IN&lang=en-IN
  - Google News India search RSS, one request per symbol (the company name in
    quotes when it is known, else "<SYMBOL> share NSE"):
    https://news.google.com/rss/search?q=...&hl=en-IN&gl=IN&ceid=IN:en
  - NSE corporate announcements RSS, ONE request for the whole market, filtered
    to your companies (board-meeting outcomes, results, resignations, credit
    ratings, acquisitions, insolvency: the Indian counterpart of an 8-K):
    https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml
    NSE sometimes refuses scripted downloads; the tool then says so and the
    headlines still run.
  - The move: Yahoo Finance's chart endpoint (unofficial, can lag), the last
    price against yesterday's close:
    https://query2.finance.yahoo.com/v8/finance/chart/<SYMBOL>.NS?range=1d&interval=5m

Times print in IST. State: trader/state/news.json remembers what you have
seen (30 days), so an item shows once. Offline: --offline DIR reads
yahoo-<SYMBOL>.xml, google-<SYMBOL>.xml, chart-<SYMBOL>.json and
nse-announcements.xml from DIR. The tests use it.

Headlines are leads, not facts: open the story before acting, and treat
nothing here as advice.
"""

import argparse
import datetime as _dt
import email.utils
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

YAHOO = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=IN&lang=en-IN"
GOOGLE = "https://news.google.com/rss/search?q=%s&hl=en-IN&gl=IN&ceid=IN:en"
NSE_ANNOUNCEMENTS = "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml"
CHART = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=5m"
BROWSER_UA = "Mozilla/5.0 (compatible; day-trader-skill/2.0; +https://github.com/Jakeschincariol/day-trader-skill)"
KEEP_DAYS = 30
MOVE_PCT = 3.0  # a stock this far from yesterday's close is flagged as moving
IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))
SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
EXCHANGE = ["NSE"]   # from trader/config.json "exchange"

# an exchange announcement whose subject matches one of these gets the "!" mark
IMPORTANT_SUBJECTS = [
    ("results", r"financial results?|outcome of board meeting|audited|unaudited|quarterly results?"),
    ("people", r"resignation|cessation|change in (?:director|management|auditor)|appointment of (?:md|ceo|cfo)"),
    ("rating", r"credit rating|rating (?:downgrade|upgrade|revision)"),
    ("deal", r"acquisition|amalgamation|merger|demerger|scheme of arrangement|open offer|takeover"),
    ("distress", r"insolvency|default|nclt|liquidation|fraud|forensic|qualified opinion|going concern"),
    ("capital", r"buy ?back|bonus|stock split|sub-?division|rights issue|qip|preferential issue|pledge"),
    ("regulatory", r"sebi (?:order|notice)|show cause|penalt|search and seizure|income tax|gst (?:demand|order)|"
                   r"suspension|delisting"),
]
KEYWORDS = [
    ("earnings", r"\bearnings\b|\bresults\b|\bQ[1-4]\b|\bPAT\b|\bnet profit\b|\bEBITDA\b|\bguidance\b|\brevenue\b"),
    ("analyst", r"\bupgrade[sd]?\b|\bdowngrade[sd]?\b|target price|price target|\boutperform\b|\bunderperform\b"
                r"|\bbrokerage\b|\bbuy rating\b|\bsell rating\b"),
    ("legal", r"\blawsuit\b|\bsued\b|\bprobe\b|\binvestigation\b|\bSEBI\b|\bED\b|\bCBI\b|\bNCLT\b|\bSupreme Court\b"
              r"|\bHigh Court\b|\bshow[- ]cause\b|\bpenalty\b"),
    ("deal", r"\bacqui(?:re|res|red|sition)\b|\bmerger\b|\bdemerger\b|\bbuyout\b|\btakeover\b|\bopen offer\b|\bstake sale\b"
             r"|\bblock deal\b|\bbulk deal\b"),
    ("capital", r"\bdividend\b|\bbuyback\b|\bbonus (?:issue|shares?)\b|\bstock split\b|\bQIP\b|\brights issue\b|\bOFS\b"
                r"|\bIPO\b|\bpledge[sd]?\b|\bpromoters?\b"),
    ("people", r"\bCEO\b|\bCFO\b|\bMD\b|\bchairman\b|\bresign|\bsteps down\b|\bappoint"),
    ("orders", r"\border win\b|\bbags? (?:an? )?order\b|\bwins? (?:an? )?(?:order|contract)\b|\bletter of (?:award|intent)\b"),
    ("risk", r"\brecall\b|\bbankrupt|\binsolvency\b|\bdefault\b|\bdelist|\bhack|\bbreach\b|\bfraud\b|\braid\b"),
    ("halt", r"\bupper circuit\b|\blower circuit\b|\bcircuit\b|\bF&O ban\b|\bASM\b|\bGSM\b|\bhalt(?:s|ed)?\b"
             r"|\btrading suspen"),
    ("regulatory", r"\bUSFDA\b|\bFDA\b|\bapproval\b|\bDCGI\b|\bTRAI\b|\bIRDAI\b|\bCCI\b|\bGST\b"),
    ("macro", r"\bRBI\b|\bMPC\b|\brepo rate\b|\bCPI\b|\binflation\b|\bFII\b|\bFPI\b|\bDII\b|\bNifty\b|\bSensex\b"
              r"|\bbudget\b|\brupee\b|\bcrude\b|\bFed\b|\btariffs?\b"),
]


class NewsError(Exception):
    pass


# ---------------------------------------------------------------- time

def ist_offset(utc=None):
    """Hours from UTC for India: always +5:30 (IST has no daylight saving)."""
    return 5.5


def to_ist(utc):
    """Aware or naive UTC -> naive IST wall-clock time."""
    if utc.tzinfo is not None:
        utc = utc.astimezone(_dt.timezone.utc)
    return utc.replace(tzinfo=None) + _dt.timedelta(hours=ist_offset(utc))


# ---------------------------------------------------------------- inputs

def load_json(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def watch_from_files(portfolio="trader/portfolio.json", watchlist="trader/watchlist.json",
                     plan="trader/plan.json"):
    """{symbol: name or None}: the scanner's hits, the planned trade and your holdings."""
    out = {}
    wl = load_json(watchlist) or {}
    for h in wl.get("hits", []):
        sym = h.get("symbol") or h.get("ticker")
        if sym:
            out[sym.upper()] = h.get("name")
    pl = load_json(plan) or {}
    if pl.get("symbol"):
        out.setdefault(pl["symbol"].upper(), pl.get("name"))
    pf = load_json(portfolio) or {}
    for p in pf.get("positions", []):
        sym = p.get("ticker") or p.get("symbol")
        if sym:
            out[sym.upper()] = p.get("name") or out.get(sym.upper())
    return out


def names_from_universe(path="trader/universe.txt"):
    """{SYMBOL: company name} from the scanner's universe file (SYMBOL|Name a line)."""
    out = {}
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln and not ln.startswith("#") and "|" in ln:
                    sym, name = ln.split("|", 1)
                    if name.strip():
                        out[sym.strip().upper()] = name.strip()
    return out


# ---------------------------------------------------------------- fetching

class Fetcher(object):
    def __init__(self, offline=None, pause=0.15):
        self.offline = offline
        self.pause = pause
        self._last = 0.0

    def get(self, url, name):
        if self.offline:
            path = os.path.join(self.offline, name)
            if not os.path.isfile(path):
                raise NewsError("offline: no file %s" % path)
            with open(path, "rb") as fh:
                return fh.read()
        gap = time.time() - self._last
        if gap < self.pause:
            time.sleep(self.pause - gap)
        self._last = time.time()
        headers = {"User-Agent": BROWSER_UA, "Accept-Encoding": "gzip", "Accept": "*/*"}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as exc:
            raise NewsError("HTTP %s for %s" % (exc.code, url))
        except urllib.error.URLError as exc:
            raise NewsError("could not reach %s: %s" % (url, exc.reason))


def yahoo_symbol(ticker):
    """RELIANCE -> RELIANCE.NS (BSE: .BO). A symbol with .NS / .BO keeps it."""
    s = ticker.strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return s + SUFFIX.get(EXCHANGE[0], ".NS")


def google_query(ticker, name=None):
    """The Google News search for one company: its name in quotes, or the symbol with NSE."""
    core = clean_name(name) if name else ""
    q = ('"%s"' % core) if len(core) >= 4 else ("%s share NSE" % ticker)
    return urllib.parse.quote(q + " when:3d")


LEGAL_WORDS = re.compile(r"\b(limited|ltd\.?|pvt\.?|private|corporation|corp\.?|company|co\.?|india|\(india\))\b",
                         re.I)


def clean_name(name):
    """"Reliance Industries Limited" -> "Reliance Industries": the part people actually write."""
    core = LEGAL_WORDS.sub(" ", name or "")
    core = re.sub(r"[^A-Za-z0-9&' -]", " ", core)
    return " ".join(core.split()).strip(" -&")


# ---------------------------------------------------------------- parsing

def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _text(el, name):
    for c in el.iter():
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def parse_time(value):
    """RFC 822 (RSS), ISO 8601, or NSE's "19-Oct-2026 10:15:30" (IST) -> aware UTC datetime, or None."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        d = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        d = None
    if d is None:
        try:
            d = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            d = None
    if d is None:
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                d = _dt.datetime.strptime(value, fmt).replace(tzinfo=IST)   # the exchange's own clock
                break
            except ValueError:
                continue
        if d is None:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.astimezone(_dt.timezone.utc)


def parse_rss(data, ticker, source="Yahoo Finance"):
    """A headline RSS feed (Yahoo Finance or Google News) -> items."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise NewsError("%s RSS for %s is not valid XML: %s" % (source, ticker, exc))
    prefix = "rss:" if source == "Yahoo Finance" else "gnews:"
    out = []
    for it in root.iter("item"):
        title = _text(it, "title")
        link = _text(it, "link")
        guid = _text(it, "guid") or link
        publisher = _text(it, "source")
        src = source
        if source != "Yahoo Finance" and publisher:
            src = publisher
            if title.endswith(" - " + publisher):        # Google appends " - Publisher" to every title
                title = title[:-len(publisher) - 3]
        summary = re.sub(r"<[^>]+>", " ", _text(it, "description"))
        out.append({"id": prefix + guid, "source": src, "kind": "headline",
                    "ticker": ticker, "title": title, "summary": " ".join(summary.split()),
                    "link": link, "time": parse_time(_text(it, "pubDate"))})
    return out


def name_patterns(watch):
    """{symbol: regex that finds the company in an announcement's title}."""
    pats = {}
    for t, name in watch.items():
        alts = [r"(?<![A-Z0-9&-])%s(?![A-Z0-9&-])" % re.escape(t)]
        core = clean_name(name) if name else ""
        if len(core) >= 4:
            alts.append(r"\b%s\b" % re.escape(core).replace(r"\ ", r"[\s-]+"))
        pats[t] = re.compile("|".join(alts), re.I)
    return pats


def parse_nse_announcements(data, watch):
    """NSE's corporate-announcements RSS (the whole market) -> items for the watched companies.

    Each item's title is the company; the description carries the subject. A company is
    matched by its symbol (as a whole word, or as symbol=... in the link) or by its name."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise NewsError("the NSE announcements feed is not valid XML: %s" % exc)
    pats = name_patterns(watch)
    out = []
    for it in root.iter("item"):
        title = _text(it, "title")
        desc = " ".join(re.sub(r"<[^>]+>", " ", _text(it, "description")).split())
        link = _text(it, "link")
        m = re.search(r"[?&]symbol=([A-Za-z0-9&%-]+)", link)
        link_sym = urllib.parse.unquote(m.group(1)).upper() if m else None
        hit = None
        for t, rx in pats.items():
            if link_sym == t or rx.search(title):
                hit = t
                break
        if hit is None:
            continue
        subject = desc
        m = re.search(r"\|\s*SUBJECT\s*:\s*(.+)$", desc, re.I)
        if m:
            subject = m.group(1).strip()
        labels = [label for label, rx in IMPORTANT_SUBJECTS if re.search(rx, desc, re.I)]
        guid = _text(it, "guid") or link or (title + desc)
        short = subject if len(subject) <= 160 else subject[:157].rstrip() + "..."
        out.append({"id": "nse:" + guid, "source": "NSE filing", "kind": "filing", "form": "announcement",
                    "ticker": hit, "title": "%s: %s" % (title or hit, short), "summary": desc,
                    "items": labels, "important": bool(labels),
                    "link": link, "time": parse_time(_text(it, "pubDate"))})
    return out


def parse_chart(data, ticker):
    """Yahoo chart JSON -> {"ticker", "price", "prev_close", "pct", "time"} or raise."""
    try:
        doc = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        meta = doc["chart"]["result"][0]["meta"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise NewsError("chart for %s is not usable" % ticker)
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if not price or not prev:
        raise NewsError("chart for %s has no price" % ticker)
    when = meta.get("regularMarketTime")
    return {"ticker": ticker, "price": round(float(price), 2), "prev_close": round(float(prev), 2),
            "pct": round((float(price) / float(prev) - 1) * 100, 2),
            "time": _dt.datetime.fromtimestamp(when, _dt.timezone.utc) if when else None}


def collect_moves(fetcher, watch, errors=None):
    errors = [] if errors is None else errors
    out = []
    for t in sorted(watch):
        name = "chart-%s.json" % t
        try:
            try:
                data = fetcher.get(CHART % ("query2", urllib.parse.quote(yahoo_symbol(t), safe=".-")), name)
            except NewsError as exc:
                if fetcher.offline or not re.search(r"HTTP (429|5\d\d)", str(exc)):
                    raise
                data = fetcher.get(CHART % ("query1", urllib.parse.quote(yahoo_symbol(t), safe=".-")), name)
            out.append(parse_chart(data, t))
        except NewsError as exc:
            if not (fetcher.offline and "no file" in str(exc)):
                errors.append("price for %s: %s" % (t, exc))
    return out


def mention_patterns(watch):
    pats = {}
    for t, name in watch.items():
        alts = [r"\(%s\)" % re.escape(t), r"\b(?:NSE|BSE)\s*:\s*%s(?![A-Z0-9&-])" % re.escape(t)]
        core = clean_name(name) if name else ""
        if len(core) >= 4:
            alts.append(r"\b%s\b" % re.escape(core).replace(r"\ ", r"[\s-]"))
        pats[t] = re.compile("|".join(alts))
    return pats


def tag(items, watch):
    """Which of your tickers each item touches, and why it matters."""
    pats = mention_patterns(watch)
    for it in items:
        hay = "%s %s" % (it["title"], it.get("summary") or "")
        touches = {it["ticker"]} if it["ticker"] in watch else set()
        for t, rx in pats.items():
            if rx.search(hay):
                touches.add(t)
        it["touches"] = sorted(touches)
        it["tags"] = [label for label, rx in KEYWORDS if re.search(rx, hay, re.I)]
        if it["kind"] == "filing" and "results" in it.get("items", []) and "earnings" not in it["tags"]:
            it["tags"].insert(0, "earnings")
    return items


def dedupe(items):
    """One item per story: same id, or same link, or same title the same day."""
    seen, out = {}, []
    for it in items:
        keys = [it["id"], it["link"],
                "%s|%s" % (re.sub(r"\W+", " ", it["title"].lower()).strip(),
                           it["time"].date() if it["time"] else "")]
        hit = next((seen[k] for k in keys if k and k in seen), None)
        if hit is not None:
            for t in it.get("touches", []):
                if t not in hit["touches"]:
                    hit["touches"].append(t)
            hit["touches"].sort()
            continue
        for k in keys:
            if k:
                seen[k] = it
        out.append(it)
    return out


def fingerprint(it):
    return hashlib.sha1(it["id"].encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- the check

def collect(fetcher, watch, state, filings=True, google=True, errors=None):
    errors = [] if errors is None else errors
    items = []
    for t in sorted(watch):
        try:
            items += parse_rss(fetcher.get(YAHOO % urllib.parse.quote(yahoo_symbol(t), safe=".-"),
                                           "yahoo-%s.xml" % t), t)
        except NewsError as exc:
            if not (fetcher.offline and "no file" in str(exc)):
                errors.append("Yahoo headlines for %s: %s" % (t, exc))
        if google:
            try:
                items += parse_rss(fetcher.get(GOOGLE % google_query(t, watch.get(t)), "google-%s.xml" % t), t,
                                   "Google News")
            except NewsError as exc:
                if not (fetcher.offline and "no file" in str(exc)):
                    errors.append("Google News for %s: %s" % (t, exc))
    if filings:
        try:
            items += parse_nse_announcements(fetcher.get(NSE_ANNOUNCEMENTS, "nse-announcements.xml"), watch)
        except NewsError as exc:
            errors.append("NSE announcements skipped (%s). NSE sometimes blocks scripted downloads: check "
                          "nseindia.com > Corporate Filings > Announcements for your symbols" % exc)
    return items


def select(items, state, now, hours=48, show_all=False):
    """Items within the window; only unseen ones unless show_all."""
    seen = state.setdefault("seen", {})
    cutoff = now - _dt.timedelta(hours=hours)
    ahead = now + _dt.timedelta(minutes=10)  # a pinned --now: nothing from after it
    out = []
    for it in items:
        if it["time"] is not None and (it["time"] < cutoff or it["time"] > ahead):
            continue
        fp = fingerprint(it)
        it["new"] = fp not in seen
        if it["new"] or show_all:
            out.append(it)
    out.sort(key=lambda i: (i["time"] or now), reverse=True)
    return out


def remember(items, state, now):
    seen = state.setdefault("seen", {})
    stamp = now.isoformat()
    for it in items:
        seen.setdefault(fingerprint(it), stamp)
    cutoff = (now - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
    state["last_check"] = stamp


def render_moves(moves, move_pct=MOVE_PCT):
    out = []
    for m in moves:
        flag = "MOVING" if abs(m["pct"]) >= move_pct else ""
        when = (" at %s IST" % to_ist(m["time"]).strftime("%H:%M")) if m.get("time") else ""
        out.append("%-10s \u20b9%s %+.2f%% vs yesterday's close \u20b9%s%s  %s" % (
            m["ticker"], "{:,.2f}".format(m["price"]), m["pct"], "{:,.2f}".format(m["prev_close"]),
            when, flag))
    return out


def render(items, errors, now, moves=None, move_pct=MOVE_PCT):
    out = render_moves(moves or [], move_pct)
    if out:
        out.append("")
    if not items:
        out.append("Nothing new.")
    for it in items:
        when = to_ist(it["time"]).strftime("%Y-%m-%d %H:%M IST") if it["time"] else "time unknown"
        mark = "!" if it.get("important") else " "
        who = ",".join(it["touches"]) or it["ticker"]
        out.append("%s %s  %-11s %-13s %s" % (mark, when, who, it["source"][:22], it["title"]))
        extra = []
        if it["tags"]:
            extra.append("tags: " + ", ".join(it["tags"]))
        extra.append(it["link"])
        out.append("      " + "  ".join(extra))
    for e in errors:
        out.append("note: %s" % e)
    out.append("Checked %s. Headlines are leads, not facts; open the story before acting. "
               "Not financial advice." % to_ist(now).strftime("%Y-%m-%d %H:%M IST"))
    return "\n".join(out) + "\n"


def _json_ready(items):
    out = []
    for it in items:
        d = dict(it)
        d["time"] = it["time"].isoformat() if it["time"] else None
        out.append(d)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tickers", nargs="*", help="default: watchlist + plan + portfolio")
    ap.add_argument("--portfolio", default="trader/portfolio.json")
    ap.add_argument("--watchlist", default="trader/watchlist.json")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--state", default="trader/state/news.json")
    ap.add_argument("--hours", type=float, default=48, help="ignore items older than this")
    ap.add_argument("--all", action="store_true", help="show seen items too")
    ap.add_argument("--no-filings", action="store_true", help="headlines only: skip NSE announcements")
    ap.add_argument("--no-google", action="store_true", help="skip the Google News search")
    ap.add_argument("--universe", default="trader/universe.txt", help="SYMBOL|Name file for company names")
    ap.add_argument("--no-moves", action="store_true", help="skip the price line per symbol")
    ap.add_argument("--move-pct", type=float, default=MOVE_PCT, help="flag a move this big (percent)")
    ap.add_argument("--config", default="trader/config.json")
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--now", help="ISO time, for reproducible runs")
    ap.add_argument("--dry-run", action="store_true", help="do not update the state file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.tickers:
        watch = {t.upper(): None for t in args.tickers}
        known = watch_from_files(args.portfolio, args.watchlist, args.plan)
        watch.update({t: known[t] for t in watch if known.get(t)})
    else:
        watch = watch_from_files(args.portfolio, args.watchlist, args.plan)
    names = names_from_universe(args.universe)
    for t in watch:
        if not watch[t] and names.get(t):
            watch[t] = names[t]
    EXCHANGE[0] = str((load_json(args.config) or {}).get("exchange") or "NSE").upper()
    if not watch:
        print("news: no symbols. Pass --tickers, or run /trader-scanner first (it writes "
              "trader/watchlist.json).", file=sys.stderr)
        return 2
    now = parse_time(args.now) if args.now else _dt.datetime.now(_dt.timezone.utc)
    state = load_json(args.state) or {}
    errors = []
    fetcher = Fetcher(offline=args.offline)
    items = collect(fetcher, watch, state, filings=not args.no_filings, google=not args.no_google, errors=errors)
    items = dedupe(tag(items, watch))
    shown = select(items, state, now, hours=args.hours, show_all=args.all)
    moves = [] if args.no_moves else collect_moves(fetcher, watch, errors)
    if args.json:
        mv = [dict(m, time=m["time"].isoformat() if m.get("time") else None,
                   moving=abs(m["pct"]) >= args.move_pct) for m in moves]
        print(json.dumps({"checked": now.isoformat(), "moves": mv, "items": _json_ready(shown),
                          "notes": errors}, indent=2))
    else:
        sys.stdout.write(render(shown, errors, now, moves, args.move_pct))
    if not args.dry_run:
        remember(items, state, now)
        folder = os.path.dirname(args.state)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(args.state, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
    return 0 if any(i["new"] for i in shown) else 1


if __name__ == "__main__":
    sys.exit(main())
