"""trader-news tests (India). Every fixture in tests/fixtures/trader-news/ is synthetic:
fictional companies and made-up headlines in the layouts of Yahoo's RSS, Google News' RSS
and NSE's corporate-announcements RSS (see the README there)."""

import datetime
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

news = load("trader-news", "news")

NDIR = os.path.join(FIX, "trader-news")
NOW = "2026-10-19T04:30:00Z"            # 10:00 IST
UTC = datetime.timezone.utc
WATCH = {"DEMO": "Demo Industries Limited", "A&B": "A & B Engineering Limited", "SOME-AUTO": None}


def read(name):
    with open(os.path.join(NDIR, name), "rb") as fh:
        return fh.read()


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = news.main(argv)
    return code, out.getvalue(), err.getvalue()


class Time(unittest.TestCase):
    def test_ist(self):
        self.assertEqual(news.to_ist(datetime.datetime(2026, 10, 19, 4, 30, tzinfo=UTC)),
                         datetime.datetime(2026, 10, 19, 10, 0))
        self.assertEqual(news.to_ist(datetime.datetime(2026, 12, 1, 4, 30)), datetime.datetime(2026, 12, 1, 10, 0))

    def test_parse_time_knows_the_exchange_format(self):
        want = datetime.datetime(2026, 10, 19, 4, 0, tzinfo=UTC)
        self.assertEqual(news.parse_time("Mon, 19 Oct 2026 04:00:00 +0000"), want)
        self.assertEqual(news.parse_time("Mon, 19 Oct 2026 04:00:00 GMT"), want)
        self.assertEqual(news.parse_time("2026-10-19T04:00:00Z"), want)
        self.assertEqual(news.parse_time("19-Oct-2026 09:30:00"), want)      # NSE's own clock is IST
        self.assertEqual(news.parse_time("19-Oct-2026 09:30"), want)
        self.assertIsNone(news.parse_time("soon"))
        self.assertIsNone(news.parse_time(""))


class Symbols(unittest.TestCase):
    def tearDown(self):
        news.EXCHANGE[0] = "NSE"

    def test_yahoo_symbol(self):
        self.assertEqual(news.yahoo_symbol("reliance"), "RELIANCE.NS")
        self.assertEqual(news.yahoo_symbol("M&M"), "M&M.NS")
        self.assertEqual(news.yahoo_symbol("TCS.BO"), "TCS.BO")
        news.EXCHANGE[0] = "BSE"
        self.assertEqual(news.yahoo_symbol("RELIANCE"), "RELIANCE.BO")

    def test_names_and_the_google_query(self):
        self.assertEqual(news.clean_name("Reliance Industries Limited"), "Reliance Industries")
        self.assertEqual(news.clean_name("Tata Consultancy Services Ltd."), "Tata Consultancy Services")
        self.assertEqual(news.clean_name("Maruti Suzuki India Limited"), "Maruti Suzuki")
        self.assertEqual(news.google_query("RELIANCE", "Reliance Industries Limited"),
                         "%22Reliance%20Industries%22%20when%3A3d")
        self.assertEqual(news.google_query("ITC", None), "ITC%20share%20NSE%20when%3A3d")
        self.assertEqual(news.google_query("ITC", "ITC Limited"), "ITC%20share%20NSE%20when%3A3d")   # too short a name

    def test_names_from_the_universe_file(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "universe.txt")
            with open(p, "w") as fh:
                fh.write("# NSE\nDEMO|Demo Industries Limited\nA&B|A & B Engineering Limited\nBARE\n")
            self.assertEqual(news.names_from_universe(p), {"DEMO": "Demo Industries Limited",
                                                           "A&B": "A & B Engineering Limited"})
            self.assertEqual(news.names_from_universe(os.path.join(d, "none")), {})
        finally:
            shutil.rmtree(d)


class Parsing(unittest.TestCase):
    def test_yahoo_rss(self):
        items = news.parse_rss(read("yahoo-DEMO.xml"), "DEMO")
        self.assertEqual(len(items), 3)
        first = items[0]
        self.assertEqual((first["id"], first["source"], first["kind"]), ("rss:demo-0001", "Yahoo Finance", "headline"))
        self.assertEqual(first["title"], "Demo Industries Q2 results preview: net profit seen up 12%")
        self.assertEqual(first["time"], datetime.datetime(2026, 10, 19, 3, 4, tzinfo=UTC))

    def test_google_news_rss_names_the_publisher(self):
        items = news.parse_rss(read("google-DEMO.xml"), "DEMO", "Google News")
        self.assertEqual([i["source"] for i in items], ["Example Business Daily", "Example Markets"])
        self.assertEqual(items[0]["title"], "Demo Industries bags order worth Rs 450 crore from a state utility")
        self.assertEqual(items[0]["id"], "gnews:gn-demo-0001")
        self.assertNotIn("<", items[0]["summary"])                   # Google's HTML is stripped

    def test_nse_announcements_are_filtered_to_your_companies(self):
        items = news.parse_nse_announcements(read("nse-announcements.xml"), WATCH)
        # SOME-AUTO has no company name here and its symbol is not in the link: it cannot be matched
        self.assertEqual([i["ticker"] for i in items], ["DEMO", "A&B"])
        named = dict(WATCH, **{"SOME-AUTO": "Some Auto Limited"})
        items = news.parse_nse_announcements(read("nse-announcements.xml"), named)
        self.assertEqual([i["ticker"] for i in items], ["DEMO", "SOME-AUTO", "A&B"])
        demo, auto, ab = items
        self.assertEqual(demo["title"], "Demo Industries Limited: Outcome of Board Meeting - Financial Results "
                                        "for the quarter ended September 30, 2026")
        self.assertEqual((demo["source"], demo["kind"], demo["important"], demo["items"]),
                         ("NSE filing", "filing", True, ["results"]))
        self.assertEqual(demo["time"], datetime.datetime(2026, 10, 19, 4, 0, tzinfo=UTC))    # 09:30 IST
        self.assertFalse(auto["important"])                          # a trading-window notice is routine
        self.assertEqual((ab["important"], ab["items"]), (True, ["people"]))   # matched by symbol=A%26B in the link
        # "Demonstration Foods" is not "Demo Industries", and DEMOFOODS is not DEMO
        self.assertNotIn("Demonstration", " ".join(i["title"] for i in items))
        self.assertEqual(news.parse_nse_announcements(read("nse-announcements.xml"), {"INFY": "Infosys Limited"}), [])
        with self.assertRaises(news.NewsError):
            news.parse_nse_announcements(b"<html>Access Denied</html><p>", WATCH)

    def test_chart_move(self):
        m = news.parse_chart(read("chart-DEMO.json"), "DEMO")
        self.assertEqual((m["price"], m["prev_close"], m["pct"]), (366.48, 354.72, 3.31))
        with self.assertRaises(news.NewsError):
            news.parse_chart(b"{}", "DEMO")


class Tagging(unittest.TestCase):
    def tag(self, title, summary="", ticker="NIFTY"):
        it = {"id": "x", "ticker": ticker, "title": title, "summary": summary, "kind": "headline", "link": "l",
              "time": None}
        return news.tag([it], WATCH)[0]

    def test_indian_market_keywords(self):
        cases = [("Infosys Q2 PAT rises 9%, revenue guidance raised", "earnings"),
                 ("SEBI issues show-cause notice to promoter entity", "legal"),
                 ("Promoters pledge 4% stake; QIP opens Monday", "capital"),
                 ("Company bags order worth Rs 800 crore", "orders"),
                 ("Stock locked in upper circuit for third day", "halt"),
                 ("Stock enters F&O ban list", "halt"),
                 ("RBI MPC keeps repo rate unchanged; Nifty slips", "macro"),
                 ("USFDA issues Form 483 to the Goa plant", "regulatory"),
                 ("Brokerage raises target price, keeps buy rating", "analyst"),
                 ("Block deal: 1.2% equity changes hands", "deal")]
        for title, want in cases:
            self.assertIn(want, self.tag(title)["tags"], title)
        self.assertEqual(self.tag("Weather update for Mumbai")["tags"], [])

    def test_touches(self):
        self.assertEqual(self.tag("Demo Industries wins a contract")["touches"], ["DEMO"])
        self.assertEqual(self.tag("Shares of the company (DEMO) rose")["touches"], ["DEMO"])
        self.assertEqual(self.tag("NSE: DEMO hits a 52-week high")["touches"], ["DEMO"])
        self.assertEqual(self.tag("A demo of the new product")["touches"], [])
        self.assertEqual(self.tag("Anything", ticker="DEMO")["touches"], ["DEMO"])

    def test_dedupe_keeps_one_story(self):
        items = news.parse_rss(read("yahoo-DEMO.xml"), "DEMO") + \
            news.parse_rss(read("google-DEMO.xml"), "DEMO", "Google News")
        out = news.dedupe(news.tag(items, WATCH))
        titles = [i["title"] for i in out]
        self.assertEqual(len(out), 4)                                # the Q2 preview came from both feeds
        self.assertEqual(titles.count("Demo Industries Q2 results preview: net profit seen up 12%"), 1)


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.state = os.path.join(self.d, "state", "news.json")
        self.uni = os.path.join(self.d, "universe.txt")
        with open(self.uni, "w") as fh:
            fh.write("DEMO|Demo Industries Limited\n")
        self.base = ["--offline", NDIR, "--state", self.state, "--now", NOW, "--universe", self.uni,
                     "--config", os.path.join(self.d, "none"), "--portfolio", os.path.join(self.d, "none"),
                     "--watchlist", os.path.join(self.d, "none"), "--plan", os.path.join(self.d, "none")]

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_new_items_show_once(self):
        code, text, err = run(["--tickers", "DEMO"] + self.base)
        self.assertEqual(code, 0, err)
        lines = text.splitlines()
        self.assertIn("DEMO       ₹366.48 +3.31% vs yesterday's close ₹354.72 at 10:37 IST  MOVING", lines[0])
        self.assertIn("! 2026-10-19 09:30 IST  DEMO        NSE filing", text)
        self.assertIn("tags: earnings", text)
        self.assertIn("Demo Industries bags order worth Rs 450 crore", text)
        self.assertIn("tags: orders", text)
        self.assertNotIn("Brokerage raises", text)                   # Friday evening: outside the 48-hour window
        self.assertNotIn("Nifty, Sensex end flat", text)
        self.assertIn("Checked 2026-10-19 10:00 IST", text)
        self.assertIn("Not financial advice", text)
        self.assertNotIn(chr(36), text)
        self.assertNotIn(" ET", text)
        # newest first
        order = [l[2:18] for l in lines if l[:1] in "! " and l[2:6] == "2026"]
        self.assertEqual(order, sorted(order, reverse=True))

        code, text, _ = run(["--tickers", "DEMO"] + self.base)
        self.assertEqual(code, 1)                                    # nothing new the second time
        self.assertIn("Nothing new.", text)
        code, text, _ = run(["--tickers", "DEMO", "--all", "--hours", "100"] + self.base)
        self.assertIn("Brokerage raises Demo Industries target price", text)
        self.assertIn("tags: analyst", text)

    def test_flags(self):
        code, text, _ = run(["--tickers", "DEMO", "--no-filings", "--no-google", "--no-moves", "--dry-run"]
                            + self.base)
        self.assertEqual(code, 0)
        self.assertNotIn("NSE filing", text)
        self.assertNotIn("bags order", text)
        self.assertNotIn("MOVING", text)
        self.assertFalse(os.path.exists(self.state))                 # --dry-run
        code, text, _ = run(["--tickers", "DEMO", "--json", "--dry-run"] + self.base)
        doc = json.loads(text)
        self.assertEqual(doc["moves"][0]["moving"], True)
        self.assertEqual(doc["items"][0]["source"], "NSE filing")
        self.assertEqual(doc["notes"], [])

    def test_a_missing_nse_feed_is_a_note_not_a_crash(self):
        d2 = os.path.join(self.d, "feeds")
        os.makedirs(d2)
        for f in ("yahoo-DEMO.xml", "chart-DEMO.json"):
            shutil.copy(os.path.join(NDIR, f), d2)
        args = ["--tickers", "DEMO", "--dry-run"] + self.base
        args[args.index("--offline") + 1] = d2
        code, text, err = run(args)
        self.assertEqual(code, 0, err)
        self.assertIn("note: NSE announcements skipped", text)
        self.assertIn("nseindia.com > Corporate Filings", text)
        self.assertIn("Demo Industries Q2 results preview", text)

    def test_symbols_from_the_trader_files(self):
        wl = os.path.join(self.d, "watchlist.json")
        with open(wl, "w") as fh:
            json.dump({"hits": [{"symbol": "demo"}]}, fh)
        args = ["--dry-run"] + self.base
        args[args.index("--watchlist") + 1] = wl
        code, text, _ = run(args)
        self.assertEqual(code, 0)
        self.assertIn("NSE filing", text)
        code, _, err = run(["--dry-run"] + self.base)
        self.assertEqual(code, 2)
        self.assertIn("no symbols", err)


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "trader-news", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("---\nname: trader-news\n"))
        low = " ".join(text.lower().split())
        for must in ("nse", "announcements", "google news", "leads, not facts", "ist", "## safety"):
            self.assertIn(must, low)
        for never in ("sec edgar", "8-k", "sec_user_agent", "new york"):
            self.assertNotIn(never, low)


if __name__ == "__main__":
    unittest.main()
