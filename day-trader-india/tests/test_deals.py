"""trader-deals tests. The fixtures are synthetic (fictional companies and clients) in the layout of
NSE's bulk.csv and block.csv."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

deals = load("trader-deals", "deals")

DDIR = os.path.join(FIX, "trader-deals")
PLAN = os.path.join(FIX, "trader-budget", "plan-demo.json")


def read(name):
    with open(os.path.join(DDIR, name), encoding="utf-8") as fh:
        return fh.read()


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = deals.main(argv)
    return code, out.getvalue(), err.getvalue()


class Parsing(unittest.TestCase):
    def test_bulk_csv(self):
        rows = deals.parse_deals(read("bulk.csv"), "bulk")
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0], {"kind": "bulk", "date": "2026-10-19", "symbol": "DEMO",
                                   "name": "Demo Industries Limited", "client": "EXAMPLE CAPITAL FUND",
                                   "side": "buy", "qty": 1250000, "price": 364.55, "value": 455687500.0,
                                   "remarks": ""})
        self.assertEqual(rows[3]["symbol"], "A&B")

    def test_columns_are_found_by_name(self):
        shuffled = ("Buy / Sell,Client Name,Symbol,Quantity,Trade Price,Date\n"
                    "S,SOMEONE,INFY,1000,1500.5,02-11-2026\n")
        r = deals.parse_deals(shuffled, "bulk")[0]
        self.assertEqual((r["side"], r["client"], r["symbol"], r["qty"], r["price"], r["date"]),
                         ("sell", "SOMEONE", "INFY", 1000, 1500.5, "2026-11-02"))
        with self.assertRaises(deals.DealsError) as cm:
            deals.parse_deals("<html><body>Access Denied</body></html>\n", "bulk")
        self.assertIn("web page instead of the CSV", str(cm.exception))
        self.assertEqual(deals.parse_deals("", "block"), [])

    def test_numbers(self):
        self.assertEqual(deals.indian(1250000), "12,50,000")
        self.assertEqual(deals.indian(310000), "3,10,000")
        self.assertEqual(deals.indian(999), "999")
        self.assertEqual(deals.indian(123456789), "12,34,56,789")
        self.assertEqual(deals.money(455687500), "₹45.57 cr")
        self.assertEqual(deals.money(5286000), "₹52.86 lakh")

    def test_select(self):
        rows = deals.parse_deals(read("bulk.csv"), "bulk") + deals.parse_deals(read("block.csv"), "block")
        self.assertEqual(len(deals.select(rows, symbols={"DEMO"})), 2)
        self.assertEqual([r["symbol"] for r in deals.select(rows, clients=["example capital"])], ["DEMO", "A&B"])
        self.assertEqual(len(deals.select(rows, side="buy", min_value_cr=100)), 1)    # the mutual fund's block buy
        self.assertEqual(deals.fingerprint(rows[0]), deals.fingerprint(dict(rows[0])))
        self.assertNotEqual(deals.fingerprint(rows[0]), deals.fingerprint(rows[1]))


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.state = os.path.join(self.d, "state", "deals.json")
        self.watch = os.path.join(self.d, "deals-watch.json")
        none = os.path.join(self.d, "none")
        self.base = ["--offline", DDIR, "--now", "2026-10-19", "--state", self.state, "--watch", self.watch,
                     "--portfolio", none, "--watchlist", none, "--plan", PLAN]

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_new_deals_show_once_with_flags(self):
        with open(self.watch, "w") as fh:
            json.dump({"clients": ["Example Mutual Fund"], "symbols": ["SMEX"]}, fh)
        code, text, _ = run(self.base)
        self.assertEqual(code, 0)
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("2026-10-19 BULK  DEMO         BUY  12,50,000 shares at ₹364.55 = "
                                            "₹45.57 cr  EXAMPLE CAPITAL FUND  [YOUR STOCK]"), lines[0])
        self.assertIn("[FOLLOWED: Example Mutual Fund]", text)
        self.assertIn("SMEX         BUY  60,000 shares at ₹88.10 = ₹52.86 lakh  ANOTHER INVESTOR  [YOUR STOCK]",
                      text)
        self.assertIn("not a tip", text)
        self.assertIn("Every buy here had a seller", text)
        self.assertNotIn(chr(36), text)
        code, text, _ = run(self.base)
        self.assertEqual(code, 1)
        self.assertIn("No new deals.", text)
        code, text, _ = run(self.base + ["--all", "--follow", "--json"])
        out = json.loads(text)
        self.assertEqual([d["client"] for d in out["deals"]], ["EXAMPLE MUTUAL FUND A/C LARGE CAP"])
        self.assertEqual(out["deals"][0]["followed"], ["Example Mutual Fund"])

    def test_filters_and_missing_files(self):
        code, text, _ = run(self.base + ["--dry-run", "--symbols", "a&b", "--kind", "bulk"])
        self.assertEqual(code, 0)
        self.assertEqual(len([l for l in text.splitlines() if l.startswith("2026")]), 1)
        self.assertFalse(os.path.exists(self.state))
        code, _, err = run(self.base + ["--follow"])
        self.assertEqual(code, 2)
        self.assertIn("--follow needs", err)
        empty = os.path.join(self.d, "empty")
        os.makedirs(empty)
        args = list(self.base)
        args[args.index("--offline") + 1] = empty
        code, _, err = run(args)
        self.assertEqual(code, 2)
        self.assertIn("Bulk & Block Deals", err)
        with open(os.path.join(empty, "bulk.csv"), "w") as fh:
            fh.write(read("bulk.csv"))
        code, text, _ = run(args + ["--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("note: offline: no", text)                     # block.csv is missing: a note


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "trader-deals", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("---\nname: trader-deals\n"))
        low = " ".join(text.lower().split())
        for must in ("bulk", "block", "not inside information", "## safety"):
            self.assertIn(must, low)


if __name__ == "__main__":
    unittest.main()
