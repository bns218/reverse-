"""trader-alerts tests (India: the NSE clock, rupee quotes).

The quote fixtures are synthetic (see tests/fixtures/trader-alerts/README.md): DEMO.NS at
366.475 as of 10:37:13 IST on Mon 2026-10-19, and three <TICKER>SYN.NS quotes as of
15:45 IST on Tue 2026-10-13."""

import datetime
import gzip
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

alerts = load("trader-alerts", "alerts")

QDIR = os.path.join(FIX, "trader-alerts")
PLAN = os.path.join(FIX, "trader-budget", "plan-demo.json")
DT = datetime.datetime
UA = "Mozilla/5.0 (compatible; day-trader-skill/2.0; +https://github.com/Jakeschincariol/day-trader-skill)"

# NSE trading holidays 2026 (weekday holidays only; Muhurat trading is not modelled)
NSE_2026 = ["2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31", "2026-04-03", "2026-04-14", "2026-05-01",
            "2026-05-28", "2026-06-26", "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-10", "2026-11-24",
            "2026-12-25"]


def ist(text):
    return alerts.parse_now(text)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = alerts.main(argv)
    return code, out.getvalue(), err.getvalue()


def plan_rules():
    with open(PLAN) as fh:
        return alerts.rules_from_plan(json.load(fh))


class Calendar(unittest.TestCase):
    def test_holidays_are_the_nse_list(self):
        self.assertEqual(sorted(alerts.NSE_HOLIDAYS), NSE_2026)
        self.assertEqual(alerts.NSE_EARLY_CLOSE, {})                 # NSE has no scheduled half days
        for d in alerts.NSE_HOLIDAYS:
            self.assertLess(datetime.date.fromisoformat(d).weekday(), 5, d)
        self.assertEqual((alerts.OPEN, alerts.CLOSE), (datetime.time(9, 15), datetime.time(15, 30)))

    def test_ist_never_changes(self):
        for when in (DT(2026, 3, 8, 7, 0), DT(2026, 11, 1, 6, 0), DT(2027, 6, 1)):
            self.assertEqual(alerts.ist_offset(when), 5.5)
        self.assertEqual(alerts.to_ist(DT(2026, 10, 19, 3, 45)), DT(2026, 10, 19, 9, 15))

    def test_parse_now(self):
        self.assertEqual(ist("2026-10-13T09:15"), DT(2026, 10, 13, 3, 45))
        self.assertEqual(ist("2026-10-19 10:00"), DT(2026, 10, 19, 4, 30))
        self.assertEqual(ist("2026-12-01T09:15"), DT(2026, 12, 1, 3, 45))       # the same offset in winter
        self.assertEqual(ist("2026-10-13T10:15:01Z"), DT(2026, 10, 13, 10, 15, 1))
        self.assertEqual(ist("2026-10-13T15:45:01+05:30"), DT(2026, 10, 13, 10, 15, 1))
        with self.assertRaises(alerts.AlertError):
            ist("tomorrow")

    def test_market_status(self):
        st = alerts.market_status(ist("2026-10-13T10:00"))
        self.assertTrue(st["open"])
        self.assertEqual((st["opens"], st["closes"]), ("09:15", "15:30"))
        self.assertFalse(alerts.market_status(ist("2026-10-13T09:14"))["open"])   # the pre-open session is not "open"
        self.assertEqual(alerts.market_status(ist("2026-10-13T09:14"))["next_open"], "2026-10-13 09:15")
        self.assertTrue(alerts.market_status(ist("2026-10-13T15:29"))["open"])
        after = alerts.market_status(ist("2026-10-13T15:30"))
        self.assertFalse(after["open"])
        self.assertEqual(after["next_open"], "2026-10-14 09:15")
        dussehra = alerts.market_status(ist("2026-10-20T11:00"))
        self.assertFalse(dussehra["open"])
        self.assertIn("Dussehra", dussehra["reason"])
        self.assertEqual(dussehra["next_open"], "2026-10-21 09:15")
        gandhi = alerts.market_status(ist("2026-10-02T11:00"))                   # a Friday holiday
        self.assertEqual(gandhi["next_open"], "2026-10-05 09:15")
        self.assertTrue(alerts.market_status(ist("2026-11-26T11:00"))["open"])   # US Thanksgiving
        self.assertTrue(alerts.market_status(ist("2026-11-27T14:00"))["open"])   # no early close in India
        self.assertEqual(alerts.market_status(ist("2026-10-17T10:00"))["reason"], "weekend")
        self.assertTrue(alerts.market_status(ist("2026-10-19T10:00"))["calendar_known"])
        self.assertFalse(alerts.market_status(ist("2027-03-01T10:00"))["calendar_known"])

    def test_extra_holidays_from_the_config(self):
        d = tempfile.mkdtemp()
        try:
            cfg = os.path.join(d, "config.json")
            with open(cfg, "w") as fh:
                json.dump({"extra_holidays": ["2027-01-26"], "exchange": "BSE"}, fh)
            alerts.apply_config(cfg)
            self.assertFalse(alerts.market_status(ist("2027-01-26T10:00"))["open"])
            self.assertEqual(alerts.yahoo_symbol("RELIANCE"), "RELIANCE.BO")
        finally:
            alerts.NSE_HOLIDAYS.pop("2027-01-26", None)
            alerts.apply_config(os.path.join(d, "none"))
            shutil.rmtree(d)
        self.assertEqual(alerts.yahoo_symbol("RELIANCE"), "RELIANCE.NS")


class Quotes(unittest.TestCase):
    def test_yahoo_fixtures(self):
        with open(os.path.join(QDIR, "yahoo-AAPLSYN.json")) as fh:
            q = alerts.parse_yahoo(fh.read(), "AAPLSYN")
        self.assertEqual((q["price"], q["prev_close"], q["currency"]), (341.27, 340.97, "INR"))
        self.assertEqual(q["time"], "2026-10-13T10:15:01Z")
        with open(os.path.join(QDIR, "yahoo-DEMO.json")) as fh:
            q = alerts.parse_yahoo(fh.read(), "DEMO")
        self.assertEqual((q["symbol"], q["price"], q["prev_close"], round(q["open"], 2)),
                         ("DEMO", 366.475, 354.72, 357.48))
        self.assertEqual(q["time"], "2026-10-19T05:07:13Z")              # 10:37:13 IST

    def test_urls_and_user_agent(self):
        self.assertEqual(alerts.UA, UA)
        self.assertEqual(alerts.yahoo_url("reliance"),
                         "https://query2.finance.yahoo.com/v8/finance/chart/RELIANCE.NS?range=1d&interval=1d")
        self.assertIn("/chart/M%26M.NS?", alerts.yahoo_url("M&M"))
        self.assertIn("/chart/BAJAJ-AUTO.NS?", alerts.yahoo_url("bajaj-auto"))
        self.assertIn("/chart/TCS.BO?", alerts.yahoo_url("TCS.BO"))
        self.assertIn("//query1.finance.yahoo.com/", alerts.yahoo_url("DEMO", alerts.YAHOO_HOSTS[1]))
        self.assertFalse(hasattr(alerts, "stooq_url"))                   # Stooq does not cover NSE: gone

    def test_offline_quotes_and_errors(self):
        q, errors = alerts.get_quotes(["AAPLSYN", "KOSYN", "ZZZZ", "NOPE"], "yahoo", QDIR)
        self.assertEqual(sorted(q), ["AAPLSYN", "KOSYN"])
        self.assertEqual(q["KOSYN"]["price"], 90.11)
        self.assertEqual(len(errors), 2)
        self.assertIn("No data found", errors[0])

    def test_offline_gz(self):
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(QDIR, "yahoo-DEMO.json"), "rb") as src:
                with gzip.open(os.path.join(d, "yahoo-DEMO.json.gz"), "wb") as dst:
                    dst.write(src.read())
            q, errors = alerts.get_quotes(["DEMO"], "yahoo", d)
            self.assertEqual((q["DEMO"]["price"], errors), (366.475, []))
        finally:
            shutil.rmtree(d)


class FakeNet(object):
    """Stands in for urllib: answers each request with the next status code."""

    def __init__(self, codes, body=None):
        self.codes, self.calls, self.sleeps, self.urls = list(codes), [], [], []
        with open(os.path.join(QDIR, "yahoo-DEMO.json")) as fh:
            self.body = body or fh.read()

    def urlopen(self, req, timeout=None):
        self.calls.append((req.full_url.split("/")[2], req.get_header("User-agent")))
        self.urls.append(req.full_url)
        code = self.codes.pop(0)
        if code != 200:
            fp = io.BytesIO(b'{"chart":{"result":null,"error":{"code":"Not Found",'
                            b'"description":"No data found, symbol may be delisted"}}}' if code == 404 else b"")
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, fp)
        return io.BytesIO(self.body.encode("utf-8"))


class Network(unittest.TestCase):
    def setUp(self):
        self.saved = (alerts._urlopen, alerts._sleep)

    def tearDown(self):
        alerts._urlopen, alerts._sleep = self.saved

    def net(self, codes):
        f = FakeNet(codes)
        alerts._urlopen = f.urlopen
        alerts._sleep = f.sleeps.append
        return f

    def hosts(self, f):
        return [h.split(".")[0] for h, _ in f.calls]

    def test_query2_first_asks_for_the_ns_symbol(self):
        f = self.net([200])
        q, errors = alerts.get_quotes(["DEMO"])
        self.assertEqual((q["DEMO"]["price"], errors), (366.475, []))
        self.assertEqual(f.calls, [("query2.finance.yahoo.com", UA)])
        self.assertIn("/chart/DEMO.NS?", f.urls[0])

    def test_one_retry_with_a_pause_on_429(self):
        f = self.net([429, 200])
        self.assertEqual(alerts.get_quotes(["DEMO"])[0]["DEMO"]["price"], 366.475)
        self.assertEqual(self.hosts(f), ["query2", "query2"])
        self.assertEqual(f.sleeps, [alerts.BACKOFF])

    def test_falls_back_to_query1_on_429_and_5xx(self):
        f = self.net([429, 429, 200])
        self.assertIn("DEMO", alerts.get_quotes(["DEMO"])[0])
        self.assertEqual(self.hosts(f), ["query2", "query2", "query1"])
        f = self.net([503, 200])
        self.assertIn("DEMO", alerts.get_quotes(["DEMO"])[0])
        self.assertEqual(self.hosts(f), ["query2", "query1"])
        f = self.net([500, 502])
        q, errors = alerts.get_quotes(["DEMO"])
        self.assertEqual(q, {})
        self.assertIn("query1.finance.yahoo.com/v8/finance/chart/DEMO.NS answered HTTP 502", errors[0])

    def test_a_404_is_yahoos_answer_and_a_403_is_not_retried(self):
        f = self.net([404])
        q, errors = alerts.get_quotes(["NOPE"])
        self.assertIn("No data found", errors[0])
        self.assertEqual(self.hosts(f), ["query2"])
        f = self.net([403])
        q, errors = alerts.get_quotes(["DEMO"])
        self.assertIn("HTTP 403", errors[0])
        self.assertEqual(self.hosts(f), ["query2"])

    def test_a_pause_between_symbols(self):
        f = self.net([200, 200])
        alerts.get_quotes(["DEMO", "AAPLSYN"])
        self.assertEqual(f.sleeps, [alerts.PAUSE])


class Rules(unittest.TestCase):
    def setUp(self):
        self.q, _ = alerts.get_quotes(["AAPLSYN", "BACSYN", "KOSYN", "DEMO"], "yahoo", QDIR)
        self.open = alerts.market_status(ist("2026-10-13T10:00"))
        self.now = ist("2026-10-13T10:00")

    def at(self, text, rules, state=None, quotes=None):
        now = ist(text)
        return alerts.evaluate(rules, self.q if quotes is None else quotes, alerts.market_status(now),
                               state or {}, now)

    def test_a_target_rings_once(self):
        rules = [{"id": "a-340", "symbol": "AAPLSYN", "type": "above", "price": 340}]
        rings, st = alerts.evaluate(rules, self.q, self.open, {}, self.now)
        self.assertEqual(len(rings), 1)
        self.assertIn("AAPLSYN is ₹341.27: at or above your alert level ₹340", rings[0]["message"])
        self.assertNotIn(chr(36), rings[0]["message"])
        rings, st = alerts.evaluate(rules, self.q, self.open, st, self.now)
        self.assertEqual(rings, [])

    def test_stop_and_rearm(self):
        rules = [{"id": "b-stop", "symbol": "BACSYN", "type": "stop", "price": 54, "rearm": True}]
        rings, st = alerts.evaluate(rules, self.q, self.open, {}, self.now)
        self.assertIn("your stop ₹54", rings[0]["message"])
        self.q["BACSYN"]["price"] = 55.0
        rings, st = alerts.evaluate(rules, self.q, self.open, st, self.now)
        self.assertEqual(rings, [])
        self.assertNotIn("b-stop", st["rung"])
        self.q["BACSYN"]["price"] = 53.5
        rings, st = alerts.evaluate(rules, self.q, self.open, st, self.now)
        self.assertEqual(len(rings), 1)

    def test_pct_move_from_previous_close(self):
        big = [{"id": "b-3", "symbol": "BACSYN", "type": "pct_move", "pct": 3}]
        self.assertEqual(alerts.evaluate(big, self.q, self.open, {}, self.now)[0], [])
        small = [{"id": "b-1", "symbol": "BACSYN", "type": "pct_move", "pct": 1, "direction": "down"}]
        rings, st = alerts.evaluate(small, self.q, self.open, {}, self.now)
        self.assertIn("-1.14%", rings[0]["message"])
        self.assertEqual(alerts.evaluate(small, self.q, self.open, st, self.now)[0], [])
        up = [{"id": "b-up", "symbol": "BACSYN", "type": "pct_move", "pct": 1, "direction": "up"}]
        self.assertEqual(alerts.evaluate(up, self.q, self.open, {}, self.now)[0], [])
        demo = [{"id": "demo-3", "symbol": "DEMO", "type": "pct_move", "pct": 3}]
        rings, _ = self.at("2026-10-19 10:37", demo)
        self.assertIn("DEMO moved +3.31% to ₹366.48 (from ₹354.72)", rings[0]["message"])

    def test_opening_bell_once_per_trading_day(self):
        rules = [{"id": "bell", "type": "opening_bell"}]
        closed = alerts.market_status(ist("2026-10-13T09:05"))             # the pre-open call auction
        self.assertEqual(alerts.evaluate(rules, {}, closed, {}, ist("2026-10-13T09:05"))[0], [])
        rings, st = alerts.evaluate(rules, {}, self.open, {}, self.now)
        self.assertIn("Opening bell: NSE is open", rings[0]["message"])
        self.assertEqual(alerts.evaluate(rules, {}, self.open, st, ist("2026-10-13T11:00"))[0], [])
        nxt = alerts.market_status(ist("2026-10-14T09:16"))
        self.assertEqual(len(alerts.evaluate(rules, {}, nxt, st, ist("2026-10-14T09:16"))[0]), 1)

    def test_the_plan_gives_a_stop_a_target_and_flat_by(self):
        rules = plan_rules()
        self.assertEqual([(r["id"], r["type"]) for r in rules],
                         [("demo-plan-stop", "stop"), ("demo-plan-target", "target"), ("demo-flat-by", "time")])
        self.assertEqual((rules[0]["price"], rules[1]["price"]), (358.3, 370.1))
        self.assertEqual((rules[2]["at"], rules[2]["label"]), ("15:15", "flat by close"))
        self.assertTrue(all(r["date"] == "2026-10-19" for r in rules))
        rings, st = self.at("2026-10-19 10:37", rules)                   # the 10:37 quote, 366.475
        self.assertEqual(rings, [])
        q = json.loads(json.dumps(self.q))
        q["DEMO"]["price"] = 358.10
        rings, st = self.at("2026-10-19 11:30", rules, st, q)
        self.assertEqual([r["id"] for r in rings], ["demo-plan-stop"])
        self.assertIn("DEMO is ₹358.10: at or below your stop ₹358.30 (plan stop: opening-range midpoint)",
                      rings[0]["message"])
        q["DEMO"]["price"] = 370.10
        self.assertEqual([r["id"] for r in self.at("2026-10-19 12:00", rules, st, q)[0]], ["demo-plan-target"])
        # a plan without flat_by: the config's, else 15:15 (not the US 15:55)
        bare = {"symbol": "X", "stop": 10.0, "target": 12.0}
        self.assertEqual(alerts.rules_from_plan(bare)[2]["at"], "15:15")
        self.assertEqual(alerts.rules_from_plan(bare, "15:00")[2]["at"], "15:00")

    def test_flat_by_rings_once_before_the_square_off(self):
        rules = plan_rules()[2:]
        self.assertEqual(self.at("2026-10-19 15:14", rules)[0], [])
        rings, st = self.at("2026-10-19 15:15", rules)
        self.assertEqual(len(rings), 1)
        self.assertIn("Flat by close: it is 15:15 IST (set for 15:15), the market closes at 15:30",
                      rings[0]["message"])
        self.assertIn("trader-broker flatten --symbol DEMO", rings[0]["message"])
        self.assertIn("squares off intraday (MIS) positions itself around 15:20", rings[0]["message"])
        self.assertEqual(self.at("2026-10-19 15:25", rules, st)[0], [])
        rings, _ = self.at("2026-10-19 15:40", rules)
        self.assertIn("the market has closed", rings[0]["message"])
        self.assertEqual(self.at("2026-10-21 15:16", rules, st)[0], [])     # plan rules: their day only

    def test_time_alerts_on_closed_days(self):
        rule = [{"id": "flat", "type": "time", "at": "15:15", "label": "flat by close", "before_close": True}]
        self.assertEqual(self.at("2026-10-17 15:16", rule)[0], [])         # Saturday: no session
        self.assertEqual(self.at("2026-10-20 15:16", rule)[0], [])         # Dussehra
        rings, st = self.at("2026-11-27 15:15", rule)                      # a full NSE day (a US half day)
        self.assertIn("set for 15:15), the market closes at 15:30", rings[0]["message"])
        rings, st = self.at("2026-12-01 15:15", rule)
        self.assertEqual(len(rings), 1)
        self.assertEqual(st["rung"]["flat"], "2026-12-01T09:45:00Z")       # 15:15 IST, summer or winter

    def test_the_example_rules_are_valid(self):
        with open(os.path.join(ROOT, "trader-alerts", "alerts.example.json")) as fh:
            rules = json.load(fh)["rules"]
        for r in rules:
            alerts.validate(r)
        self.assertEqual([r for r in rules if r["id"].startswith("demo-plan") or r["id"] == "demo-flat-by"],
                         [dict(r, date="2026-10-19") for r in plan_rules()])

    def test_bad_rules(self):
        with self.assertRaises(alerts.AlertError):
            alerts.evaluate([{"id": "x", "type": "moon"}], {}, self.open, {}, self.now)
        with self.assertRaises(alerts.AlertError):
            alerts.evaluate([{"id": "x", "type": "above", "symbol": "DEMO"}], {}, self.open, {}, self.now)
        with self.assertRaises(alerts.AlertError):
            alerts.evaluate([{"id": "x", "type": "time", "at": "3pm"}], {}, self.open, {}, self.now)
        with self.assertRaises(alerts.AlertError):
            alerts.rules_from_plan({"symbol": "DEMO", "stop": 358.3})


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.rules = os.path.join(self.d, "alerts.json")
        self.state = os.path.join(self.d, "state", "alerts.json")
        self.prices = os.path.join(self.d, "prices.json")
        self.none = os.path.join(self.d, "none")

    def tearDown(self):
        shutil.rmtree(self.d)

    def check(self, now):
        return run(["check", "--rules", self.rules, "--state", self.state, "--prices-out", self.prices,
                    "--offline", QDIR, "--now", now])

    def test_the_demo_trade_from_the_plan(self):
        code, text, _ = run(["add", "--from-plan", "--plan", PLAN, "--rules", self.rules, "--state", self.state,
                             "--config", self.none])
        self.assertEqual(code, 0)
        self.assertIn("Added demo-flat-by", text)
        self.assertEqual(run(["add", "--rules", self.rules, "--opening-bell"])[0], 0)

        code, text, _ = self.check("2026-10-19 10:37")
        self.assertEqual(code, 0)                                      # the opening bell rings first
        code, text, _ = self.check("2026-10-19 10:38")
        self.assertEqual(code, 1)
        self.assertIn("Nothing hit. 4 rule(s) watched today, DEMO ₹366.48.", text)
        with open(self.prices) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["prices"], {"DEMO": 366.475})
        self.assertEqual(doc["detail"]["DEMO"]["time"], "2026-10-19T05:07:13Z")
        self.assertEqual(doc["detail"]["DEMO"]["fetched"], "2026-10-19T05:08:00Z")
        self.assertEqual(doc["detail"]["DEMO"]["prev_close"], 354.72)       # trader-risk's circuit check reads this

        code, text, _ = self.check("2026-10-19 15:15")
        self.assertEqual(code, 0)
        self.assertIn("ALERT Flat by close", text)
        self.assertIn("not an order", text)
        self.assertEqual(self.check("2026-10-19 15:17")[0], 1)
        code, text, _ = self.check("2026-10-21 10:00")                 # Oct 20 is Dussehra
        self.assertIn("ALERT Opening bell", text)
        code, text, _ = self.check("2026-10-21 10:05")
        self.assertIn("Nothing hit. 1 rule(s) watched today.", text)

        # a new plan replaces the plan rules and re-arms them
        code, text, _ = run(["add", "--from-plan", "--plan", PLAN, "--rules", self.rules, "--state", self.state,
                             "--config", self.none])
        with open(self.rules) as fh:
            ids = [r["id"] for r in json.load(fh)["rules"]]
        self.assertEqual(sorted(ids), ["demo-flat-by", "demo-plan-stop", "demo-plan-target", "opening-bell"])
        with open(self.state) as fh:
            self.assertNotIn("demo-flat-by", json.load(fh)["rung"])

    def test_evening_and_morning(self):
        for args in (["--opening-bell"], ["--symbol", "AAPLSYN", "--above", "350"],
                     ["--symbol", "BACSYN", "--stop", "50"]):
            code, _, _ = run(["add", "--rules", self.rules] + args)
            self.assertEqual(code, 0)
        code, _, err = run(["add", "--rules", self.rules, "--symbol", "AAPLSYN", "--above", "350"])
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

        code, text, _ = self.check("2026-10-13T15:45")
        self.assertEqual(code, 1)
        self.assertIn("Nothing hit", text)
        with open(self.prices) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["prices"], {"AAPLSYN": 341.27, "BACSYN": 53.96})

        code, text, _ = self.check("2026-10-14T09:16")
        self.assertEqual(code, 0)
        self.assertIn("ALERT Opening bell", text)
        code, text, _ = self.check("2026-10-14T09:30")
        self.assertEqual(code, 1)

        code, text, _ = run(["list", "--rules", self.rules, "--state", self.state])
        self.assertIn("rang", text)
        self.assertEqual(run(["reset", "opening-bell", "--state", self.state])[0], 0)
        self.assertEqual(run(["reset", "opening-bell", "--state", self.state])[0], 1)

    def test_add_time_and_target(self):
        code, text, _ = run(["add", "--rules", self.rules, "--at", "15:15", "--label", "flat by close",
                             "--before-close", "--symbol", "demo"])
        self.assertEqual(code, 0)
        code, text, _ = run(["add", "--rules", self.rules, "--symbol", "DEMO", "--target", "370.10",
                             "--date", "2026-10-19"])
        self.assertEqual(code, 0)
        with open(self.rules) as fh:
            rules = json.load(fh)["rules"]
        self.assertEqual(rules[0], {"id": "time-1515", "type": "time", "at": "15:15", "label": "flat by close",
                                    "symbol": "DEMO", "before_close": True})
        self.assertEqual((rules[1]["symbol"], rules[1]["type"], rules[1]["price"], rules[1]["date"]),
                         ("DEMO", "target", 370.1, "2026-10-19"))
        self.assertEqual(run(["add", "--rules", self.rules, "--at", "3pm"])[0], 1)
        code, _, err = run(["add", "--rules", self.rules, "--from-plan", "--plan", self.none])
        self.assertEqual(code, 1)
        self.assertIn("no plan", err)

    def test_quote_write_merges(self):
        code, text, _ = run(["quote", "AAPLSYN", "KOSYN", "--offline", QDIR, "--write", self.prices,
                             "--now", "2026-10-13T10:15:01Z"])
        self.assertEqual(code, 0)
        self.assertIn("AAPLSYN ₹341.27", text)
        self.assertIn("delayed", text)
        self.assertNotIn(chr(36), text)
        run(["quote", "BACSYN", "--offline", QDIR, "--write", self.prices])
        with open(self.prices) as fh:
            doc = json.load(fh)
        self.assertEqual(sorted(doc["prices"]), ["AAPLSYN", "BACSYN", "KOSYN"])
        self.assertEqual(doc["detail"]["KOSYN"]["prev_close"], 89.79)
        self.assertEqual(doc["detail"]["KOSYN"]["fetched"], "2026-10-13T10:15:01Z")

    def test_quote_holdings_from_portfolio_and_plan(self):
        pf = os.path.join(self.d, "portfolio.json")
        with open(pf, "w") as fh:
            json.dump({"cash": 0, "positions": [{"ticker": "KOSYN", "shares": 1}]}, fh)
        code, text, _ = run(["quote", "--holdings", "--portfolio", pf, "--plan", PLAN, "--offline", QDIR, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(json.loads(text)["quotes"]), ["DEMO", "KOSYN"])

    def test_clock_exit_codes(self):
        code, text, _ = run(["clock", "--now", "2026-10-19 10:00"])
        self.assertEqual(code, 0)
        self.assertIn("NSE", text)
        self.assertNotIn("NYSE", text)
        code, text, _ = run(["clock", "--now", "2026-12-25T10:00"])
        self.assertEqual(code, 1)
        self.assertIn("NSE holiday: Christmas", text)
        self.assertIn("Next open: 2026-12-28 09:15 IST", text)

    def test_check_without_rules(self):
        code, _, err = run(["check", "--rules", self.rules, "--offline", QDIR])
        self.assertEqual(code, 1)
        self.assertIn("no rules", err)


if __name__ == "__main__":
    unittest.main()
