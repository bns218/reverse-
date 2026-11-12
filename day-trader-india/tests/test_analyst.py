"""trader-analyst tests (India). tests/fixtures/trader-analyst/ holds a SYNTHETIC company's
quarterly numbers in the shape of Yahoo's fundamentals time series (see the README there)."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

facts = load("trader-analyst", "facts")

ADIR = os.path.join(FIX, "trader-analyst")


def doc(name="DEMO"):
    with open(os.path.join(ADIR, "timeseries-%s.json" % name)) as fh:
        return json.load(fh)


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = facts.main(argv)
    return code, out.getvalue(), err.getvalue()


class Parsing(unittest.TestCase):
    def test_quarterly_series_only(self):
        s, currency = facts.series_from(doc())
        self.assertEqual(currency, "INR")
        self.assertEqual(len(s["revenue"]), 10)                      # the null pad is skipped
        self.assertEqual(s["revenue"]["2026-09-30"], 5420e7)
        self.assertEqual(s["eps_diluted"]["2026-09-30"], 11.8)
        self.assertNotIn("2026-03-31x", s["revenue"])
        self.assertEqual(s["revenue"]["2026-03-31"], 5300e7)          # the 12M annual value is ignored

    def test_not_a_timeseries_answer(self):
        with self.assertRaises(facts.FactsError):
            facts.series_from({"chart": {}})
        with self.assertRaises(facts.FactsError):
            facts.analyse(doc("NEWCO"))

    def test_indian_fiscal_quarters(self):
        self.assertEqual(facts.fiscal_label("2026-06-30"), "Q1 FY27")
        self.assertEqual(facts.fiscal_label("2026-09-30"), "Q2 FY27")
        self.assertEqual(facts.fiscal_label("2026-12-31"), "Q3 FY27")
        self.assertEqual(facts.fiscal_label("2027-03-31"), "Q4 FY27")
        self.assertEqual(facts.fiscal_label("2026-03-31"), "Q4 FY26")

    def test_symbols(self):
        self.assertEqual(facts.yahoo_symbol("reliance"), "RELIANCE.NS")
        self.assertEqual(facts.yahoo_symbol("RELIANCE", "BSE"), "RELIANCE.BO")
        self.assertEqual(facts.bare("TCS.BO"), "TCS")
        self.assertIn("type=quarterlyTotalRevenue,quarterlyGrossProfit", facts.ts_query())


class Analysis(unittest.TestCase):
    def setUp(self):
        self.r = facts.analyse(doc(), quarters=6, name="Demo Industries Limited")

    def test_the_latest_quarter(self):
        cur = self.r["rows"][0]
        self.assertEqual((cur["end"], cur["fiscal"]), ("2026-09-30", "Q2 FY27"))
        self.assertEqual((cur["revenue"], cur["net_income"], cur["eps_diluted"]), (5420e7, 590e7, 11.8))
        self.assertEqual((cur["gross_margin"], cur["operating_margin"], cur["net_margin"]), (40.6, 15.9, 10.9))
        self.assertEqual((cur["revenue_yoy"], cur["net_income_yoy"], cur["eps_yoy"]), (13.2, 22.9, 22.9))
        self.assertEqual(len(self.r["rows"]), 6)
        self.assertEqual([r["end"] for r in self.r["rows"]], sorted([r["end"] for r in self.r["rows"]], reverse=True))

    def test_ttm_and_the_oldest_rows_without_a_year_earlier(self):
        self.assertEqual(self.r["ttm"], {"revenue": 20720e7, "net_income": 2170e7, "eps_diluted": 43.4})
        old = facts.analyse(doc(), quarters=10)["rows"][-1]
        self.assertEqual((old["end"], old["revenue_yoy"]), ("2024-06-30", None))

    def test_changes_in_plain_words(self):
        lines = facts.changes(self.r)
        self.assertEqual(lines[0], "Q2 FY27 (quarter ending 2026-09-30): revenue ₹5,420 cr (+13.2% vs a year "
                                   "earlier), net profit ₹590 cr (+22.9%), diluted EPS ₹11.80 (+22.9%).")
        self.assertIn("Operating margin 15.9% (+0.5 points vs the quarter before).", lines)
        self.assertTrue(lines[-1].startswith("Revenue +7.3% vs the quarter before"))

    def test_other_income_warning(self):
        d = doc()
        for res in d["timeseries"]["result"]:
            if res["meta"]["type"][0] == "quarterlyNetIncome":
                res["quarterlyNetIncome"][-1]["reportedValue"]["raw"] = 900e7      # above operating profit
        lines = facts.changes(facts.analyse(d))
        self.assertTrue(any("other income or exceptional items" in l for l in lines))

    def test_money_in_crore(self):
        self.assertEqual(facts.money(5420e7), "₹5,420 cr")
        self.assertEqual(facts.money(12.5e7), "₹12.50 cr")
        self.assertEqual(facts.money(None), "n/a")
        self.assertEqual(facts.money(5e8, "USD"), "USD 500.0M")
        self.assertEqual(facts.pct(-50, -100), 50.0)                  # a smaller loss is an improvement


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.uni = os.path.join(self.d, "universe.txt")
        with open(self.uni, "w") as fh:
            fh.write("DEMO|Demo Industries Limited\n")
        self.base = ["--offline", ADIR, "--config", os.path.join(self.d, "none"), "--universe", self.uni]

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_report(self):
        code, text, err = run(["DEMO", "--quarters", "4"] + self.base)
        self.assertEqual(code, 0, err)
        self.assertIn("Demo Industries Limited (DEMO). ₹ crore except EPS.", text)
        self.assertIn("2026-09-30  Q2 FY27        5,420   +13.2%   40.6%   15.9%   10.9%        590    11.80  +22.9%",
                      text)
        self.assertIn("Last 4 quarters: revenue ₹20,720 cr, net profit ₹2,170 cr, diluted EPS ₹43.40.", text)
        self.assertIn("nseindia.com > Corporate Filings > Financial Results for DEMO", text)
        self.assertIn("not advice", text)
        self.assertNotIn(chr(36), text)
        self.assertNotIn("SEC", text)

    def test_json_metrics_and_errors(self):
        m = os.path.join(self.d, "trader", "metrics.json")
        code, text, _ = run(["demo.ns", "NEWCO", "--json", "--metrics", m] + self.base)
        self.assertEqual(code, 1)                                    # NEWCO has no numbers
        out = json.loads(text)
        self.assertEqual(sorted(out["results"]), ["DEMO"])
        self.assertIn("NEWCO", out["errors"][0])
        with open(m) as fh:
            row = json.load(fh)["companies"][0]
        self.assertEqual((row["ticker"], row["fiscal"], row["eps_ttm"], row["revenue_growth_yoy"], row["currency"]),
                         ("DEMO", "Q2 FY27", 43.4, 13.2, "INR"))
        code, _, err = run(["NOPE"] + self.base)
        self.assertEqual(code, 1)
        self.assertIn("no timeseries-NOPE.json", err)


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "trader-analyst", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("---\nname: trader-analyst\n"))
        low = " ".join(text.lower().split())
        for must in ("crore", "fy", "nseindia.com", "yahoo", "## safety"):
            self.assertIn(must, low)
        for never in ("xbrl", "sec_user_agent", "10-q", "8-k"):
            self.assertNotIn(never, low)


if __name__ == "__main__":
    unittest.main()
