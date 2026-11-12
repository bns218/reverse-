import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

size = load("trader-budget", "size")

CFG = os.path.join(ROOT, "trader-budget", "config.example.json")
PLAN = os.path.join(FIX, "trader-budget", "plan-demo.json")
TARGETS = os.path.join(ROOT, "trader-budget", "targets.example.json")
TOP5 = os.path.join(FIX, "trader-budget", "weights-top5.json")
NOW = "2026-10-19 10:00"
TODAY = "2026-10-19"
REEL_V1 = {"RELIANCE": 1250, "HDFCBANK": 1119, "ICICIBANK": 823, "INFY": 708, "TCS": 600}
PRICES = {"RELIANCE": 341.27, "HDFCBANK": 309.84, "ICICIBANK": 353.78, "INFY": 90.11, "TCS": 53.96}
# the India config, key for key
CONTRACT_CFG = {
    "budget": 100000, "cash_buffer_pct": 10, "max_position_pct": 75, "max_order_inr": 75000, "min_order_inr": 500,
    "max_loss_per_trade_inr": 1000, "max_daily_loss_inr": 3000, "max_trades_per_day": 3, "max_orders_per_day": 10,
    "min_reward_risk": 1.0, "require_stop": True,
    "no_entries_before": "09:30", "no_entries_after": "14:45", "flat_by": "15:15",
    "fractional": False, "exchange": "NSE", "product": "MIS", "tick_size": "nse",
    "broker": "zerodha", "paper": True, "blocked": [],
    "allow_options": False, "allow_margin": False, "intraday_leverage": 1, "allow_short": False,
    "include_charges": True,
    "charges": {"brokerage_pct": 0.03, "brokerage_max_inr": 20, "stt_sell_pct": 0.025, "exchange_txn_pct": 0.00297,
                "sebi_pct": 0.0001, "stamp_buy_pct": 0.003, "gst_pct": 18},
    "extra_holidays": [],
}
# v1's rules, for the weights mode tests
V1 = {"budget": 5000, "cash_buffer_pct": 10, "max_position_pct": 25, "max_order_inr": 2000, "min_order_inr": 5,
      "fractional": True, "paper": True, "blocked": []}


def cfg(**over):
    with open(CFG) as fh:
        c = json.load(fh)
    c.update(over)
    return c


def v1(**over):
    c = dict(V1)
    c.update(over)
    return c


def plan(**over):
    with open(PLAN) as fh:
        p = json.load(fh)
    p.update(over)
    return p


def rows(path):
    with open(path) as fh:
        return size.parse_weights(json.load(fh))


def rupees(result):
    return {p["ticker"]: p["rupees"] for p in result["positions"]}


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = size.main(argv)
    return code, out.getvalue(), err.getvalue()


def prices_doc(price, quote_time="2026-10-19T04:52:13Z"):
    return {"as_of": quote_time, "source": "yahoo", "prices": {"DEMO": price},
            "detail": {"DEMO": {"prev_close": 354.72, "time": quote_time, "source": "yahoo"}}}


class TheDemo(unittest.TestCase):
    """Rs 1,00,000, 10% buffer, Rs 1,000 max loss, DEMO risk 5.88 -> 159 shares once charges are counted."""

    def test_config_example_is_the_contract(self):
        with open(CFG) as fh:
            self.assertEqual(json.load(fh), CONTRACT_CFG)
        for k, v in size.CHARGES.items():
            self.assertEqual(CONTRACT_CFG["charges"][k], v, k)      # the example shows the built-in rates

    def test_demo_is_159_shares_bound_by_the_max_loss(self):
        s = size.size_trade(plan(), cfg(), today=TODAY)
        self.assertEqual(s["qty"], 159)
        self.assertEqual(s["bound_by"], "max loss")
        self.assertEqual(s["risk_per_share"], 5.88)
        self.assertEqual(s["cost"], 57904.62)
        self.assertEqual(s["max_loss"], 934.92)                    # 159 x 5.88
        self.assertEqual(s["max_loss_with_charges"], 995.72)       # ... plus 60.80 of charges, under 1,000
        self.assertEqual(s["gain_at_target_after_charges"], 879.26)
        self.assertEqual(s["reward_risk"], 1.01)
        self.assertEqual(s["cash_buffer"], 10000)
        self.assertEqual((s["exchange"], s["product"], s["leverage"], s["margin_needed"]), ("NSE", "MIS", 1.0, 57904.62))
        self.assertEqual([(l["name"], l["shares"]) for l in s["limits"]],
                         [("max loss", 159), ("position cap", 205), ("max order", 205), ("cash", 247)])
        self.assertEqual([l["name"] for l in s["limits"] if l["binds"]], ["max loss"])
        self.assertIsNone(s["refusal"])
        # one more share would break the max loss once charges are in
        self.assertGreater(160 * 5.88 + size.charges_for(160, 364.18, 358.3)["total"], 1000)

    def test_indian_intraday_charges(self):
        self.assertEqual(size.charges_for(159, 364.18, 358.3),
                         {"brokerage": 34.46, "stt": 14.24, "exchange": 3.41, "sebi": 0.11, "stamp": 1.74,
                          "gst": 6.84, "total": 60.8})
        # by hand, 100 shares bought at 1,000 and sold at 1,010: turnover 1,00,000 + 1,01,000
        c = size.charges_for(100, 1000, 1010)
        self.assertEqual(c["brokerage"], 40.0)      # 0.03% is Rs 30 and 30.30: capped at Rs 20 an order
        self.assertEqual(c["stt"], 25.25)           # 0.025% of the sell side
        self.assertEqual(c["exchange"], 5.97)       # 0.00297% of both sides
        self.assertEqual(c["sebi"], 0.2)            # Rs 10 a crore
        self.assertEqual(c["stamp"], 3.0)           # 0.003% of the buy side
        self.assertEqual(c["gst"], 8.31)            # 18% of brokerage + exchange + SEBI
        self.assertEqual(c["total"], 82.73)
        zero = size.charges_for(100, 1000, 1010, {"charges": {"brokerage_pct": 0}})   # a zero-brokerage plan
        self.assertEqual((zero["brokerage"], zero["total"]), (0.0, 35.53))
        self.assertEqual(size.charges_for(0, 1000, 1010)["total"], 0.0)
        # without the charge maths the old rule is back: floor(1000 / 5.88)
        s = size.size_trade(plan(), cfg(include_charges=False), today=TODAY)
        self.assertEqual((s["qty"], s["max_loss"], s["max_loss_with_charges"], s["charges_at_stop"]),
                         (170, 999.6, 999.6, None))

    def test_intraday_leverage_needs_allow_margin(self):
        wide = dict(max_loss_per_trade_inr=5000, max_position_pct=500, max_order_inr=500000, intraday_leverage=5)
        s = size.size_trade(plan(), cfg(**wide), today=TODAY)      # allow_margin is false: no leverage
        self.assertEqual((s["qty"], s["bound_by"], s["leverage"]), (247, "cash", 1.0))
        s = size.size_trade(plan(), cfg(allow_margin=True, **wide), today=TODAY)
        self.assertEqual((s["qty"], s["bound_by"], s["leverage"], s["margin_needed"]), (824, "max loss", 5.0, 60016.86))
        self.assertEqual(dict((l["name"], l["shares"]) for l in s["limits"])["cash"], 1235)
        with self.assertRaises(size.SizeError) as e:
            size.size_trade(plan(), cfg(allow_margin=True, intraday_leverage=10), today=TODAY)
        self.assertIn("between 1 and 5", str(e.exception))

    def test_the_proposed_order(self):
        o = size.bracket_order(size.size_trade(plan(), cfg(), today=TODAY))
        why = o.pop("why")
        self.assertEqual(o, {
            "symbol": "DEMO", "exchange": "NSE", "product": "MIS", "side": "buy", "qty": "159", "type": "market",
            "time_in_force": "day",
            "order_class": "bracket", "take_profit_limit_price": "370.10", "stop_loss_stop_price": "358.30",
            "plan": {"entry": 364.18, "stop": 358.3, "target": 370.1, "risk_per_share": 5.88,
                     "max_loss": 934.92, "max_loss_with_charges": 995.72, "charges_at_stop": 60.8,
                     "margin_needed": 57904.62, "setup": "orb", "entry_time": "10:00 AM", "flat_by": "15:15"}})
        self.assertIn("bound by your \u20b91,000 max loss", why)
        self.assertIn("\u20b9934.92", why)

    def test_the_fixture_orders_file_is_what_it_writes(self):
        with open(os.path.join(FIX, "trader-risk", "orders-demo.json")) as fh:
            fixture = json.load(fh)["orders"][0]
        self.assertEqual(size.bracket_order(size.size_trade(plan(), cfg(), today=TODAY)), fixture)

    def test_a_limit_order(self):
        o = size.bracket_order(size.size_trade(plan(), cfg(), limit=364.18, today=TODAY))
        self.assertEqual((o["type"], o["limit_price"], o["qty"]), ("limit", "364.18", "159"))
        s = size.size_trade(plan(), cfg(), limit=364.00, today=TODAY)
        self.assertEqual((s["risk_per_share"], s["qty"], s["max_loss"]), (5.7, 164, 934.8))
        self.assertEqual(size.bracket_order(s)["limit_price"], "364.00")

    def test_cli_writes_one_order(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "trader", "orders.json")
            code, text, _ = run(["--plan", PLAN, "--config", CFG, "--portfolio", os.path.join(d, "none"),
                                 "--now", NOW, "--write", out])
            self.assertEqual(code, 0)
            self.assertIn("Size: 159 shares of DEMO = \u20b957,904.62 at 364.18", text)
            self.assertIn("159 x 5.88 = \u20b9934.92", text)
            self.assertIn("STT \u20b914.24", text)
            self.assertIn("Loss at the stop with charges: \u20b9995.72", text)
            self.assertIn("buy 159 DEMO on NSE, MIS, market, day, target 370.10, stop-loss 358.30", text)
            self.assertIn("circuit limit", text)
            self.assertIn("<- binds", text)
            self.assertIn("not financial advice", text)
            self.assertNotIn(chr(36), text)                 # no dollar signs anywhere
            with open(out) as fh:
                doc = json.load(fh)
            self.assertEqual(doc["status"], "proposed")
            self.assertIs(doc["paper"], True)
            self.assertEqual(doc["created_at"], "2026-10-19T04:30:00Z")
            self.assertEqual(len(doc["orders"]), 1)
            self.assertEqual(doc["orders"][0]["plan"]["max_loss"], 934.92)

    def test_cli_json_and_limit(self):
        code, text, _ = run(["--plan", PLAN, "--config", CFG, "--portfolio", "/nonexistent", "--now", NOW,
                             "--limit", "--json"])
        self.assertEqual(code, 0)
        out = json.loads(text)
        self.assertEqual(out["sizing"]["qty"], 159)
        self.assertEqual(out["orders"][0]["limit_price"], "364.18")


class PlanRules(unittest.TestCase):
    def test_zero_shares_is_a_plain_refusal(self):
        s = size.size_trade(plan(stop=300.0), cfg(max_loss_per_trade_inr=50), today=TODAY)
        self.assertEqual(s["qty"], 0)
        self.assertIn("plus charges, more than your \u20b950 max loss per trade", s["refusal"])
        self.assertIsNone(size.bracket_order(s))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "plan.json")
            with open(p, "w") as fh:
                json.dump(plan(stop=300.0), fh)
            c = os.path.join(d, "config.json")
            with open(c, "w") as fh:
                json.dump(cfg(max_loss_per_trade_inr=50), fh)
            out = os.path.join(d, "orders.json")
            code, text, _ = run(["--plan", p, "--config", c, "--portfolio", os.path.join(d, "none"),
                                 "--now", NOW, "--write", out])
            self.assertEqual(code, 1)
            self.assertIn("No order:", text)
            self.assertFalse(os.path.exists(out))

    def test_each_limit_can_bind(self):
        s = size.size_trade(plan(), cfg(max_order_inr=20000), today=TODAY)
        self.assertEqual((s["qty"], s["bound_by"]), (54, "max order"))
        s = size.size_trade(plan(), cfg(max_position_pct=20), today=TODAY)
        self.assertEqual((s["qty"], s["bound_by"]), (54, "position cap"))
        s = size.size_trade(plan(), cfg(), cash=24000, today=TODAY)
        self.assertEqual((s["qty"], s["bound_by"], s["cash_available"]), (38, "cash", 14000))
        s = size.size_trade(plan(), cfg(max_loss_per_trade_inr=2000), today=TODAY)
        self.assertEqual((s["qty"], s["bound_by"]), (205, "position cap"))

    def test_a_fresh_higher_price_means_a_bigger_risk(self):
        s = size.size_trade(plan(), cfg(min_reward_risk=0), price=366.475, today=TODAY)
        self.assertEqual((s["entry"], s["entry_from"], s["risk_per_share"]), (366.48, "price", 8.18))
        self.assertEqual((s["qty"], s["max_loss"], s["reward_risk"]), (116, 948.88, 0.44))
        self.assertIsNone(s["refusal"])
        s = size.size_trade(plan(), cfg(), price=366.475, today=TODAY)
        self.assertIn("reward:risk 0.44 (target 370.10, entry 366.48, stop 358.30) is under your minimum 1",
                      s["refusal"])
        self.assertIsNone(size.bracket_order(s))
        lower = size.size_trade(plan(), cfg(), price=363.00, today=TODAY)
        self.assertEqual((lower["entry"], lower["qty"]), (364.18, 159))

    def test_prices_file_is_used_only_when_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            pp = os.path.join(d, "prices.json")
            with open(pp, "w") as fh:
                json.dump(prices_doc(366.475), fh)
            base = ["--plan", PLAN, "--config", CFG, "--portfolio", os.path.join(d, "none"), "--prices", pp, "--json"]
            code, text, _ = run(base + ["--now", "2026-10-19 10:25"])
            out = json.loads(text)
            self.assertEqual((code, out["sizing"]["qty"], out["orders"]), (1, 116, []))
            self.assertIn("above the plan's entry", out["notes"][0])
            self.assertIn("as of 10:22 IST", out["notes"][0])
            out = json.loads(run(base + ["--now", "2026-10-19 11:00"])[1])
            self.assertEqual(out["sizing"]["qty"], 159)
            self.assertIn("not used", out["notes"][0])

    def test_the_portfolio_cash_caps_the_size(self):
        with tempfile.TemporaryDirectory() as d:
            pf = os.path.join(d, "portfolio.json")
            with open(pf, "w") as fh:
                json.dump({"cash": 24000, "positions": []}, fh)
            out = json.loads(run(["--plan", PLAN, "--config", CFG, "--portfolio", pf, "--now", NOW, "--json"])[1])
            self.assertEqual((out["sizing"]["qty"], out["sizing"]["bound_by"]), (38, "cash"))

    def test_bad_plans(self):
        for p, word in ((plan(stop=365.0), "not below the entry"),
                        (plan(target=360.0), "already happened"),
                        (plan(target=None), "positive target"),
                        (plan(side="sell"), "long (buy) day trades only"),
                        (plan(symbol=""), "no symbol")):
            with self.assertRaises(size.SizeError) as e:
                size.size_trade(p, cfg(), today=TODAY)
            self.assertIn(word, str(e.exception))
        with self.assertRaises(size.SizeError) as e:
            size.size_trade(plan(), cfg(), price=371.00, today=TODAY)
        self.assertIn("already happened", str(e.exception))
        with self.assertRaises(size.SizeError) as e:
            size.size_trade(plan(), cfg(blocked=["demo"]), today=TODAY)
        self.assertIn("blocked list", str(e.exception))
        with self.assertRaises(size.SizeError) as e:
            size.size_trade(plan(), cfg(), today="2026-10-21")
        self.assertIn("make a new plan", str(e.exception))

    def test_under_the_minimum_order(self):
        cheap = plan(symbol="ABC", entry=40.0, stop=30.0, target=50.0)
        s = size.size_trade(cheap, cfg(max_loss_per_trade_inr=20), today=TODAY)
        self.assertEqual(s["qty"], 1)
        self.assertIn("under your \u20b9500 minimum order", s["refusal"])
        self.assertIsNone(size.bracket_order(s))

    def test_missing_plan_and_weights_only_flags(self):
        code, _, err = run(["--plan", "/nonexistent/plan.json", "--config", CFG, "--now", NOW])
        self.assertEqual(code, 1)
        self.assertIn("no plan", err)
        code, _, err = run(["--plan", PLAN, "--config", CFG, "--now", NOW, "--top", "2"])
        self.assertEqual(code, 1)
        self.assertIn("--weights", err)
        code, _, err = run(["--plan", PLAN, "--config", CFG, "--now", "tomorrow"])
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)


class WeightsMode(unittest.TestCase):
    """v1's split, kept behind --weights / --targets: ₹5,000, 10% cash, 25% cap."""

    def check_reel(self, r):
        self.assertEqual(rupees(r), REEL_V1)
        self.assertEqual(r["cash_buffer"], 500)
        self.assertEqual(r["invested"], 4500)
        self.assertEqual(r["idle"], 0)
        self.assertEqual(r["cap"], 1250)
        self.assertEqual([p["ticker"] for p in r["positions"] if p["capped"]], ["RELIANCE"])

    def test_from_the_raw_weights(self):
        self.check_reel(size.size(rows(TOP5), v1()))

    def test_from_the_renormalised_weights_file(self):
        self.check_reel(size.size(rows(TARGETS), v1()))

    def test_from_inline_weights(self):
        w = size.parse_weights(size.weights_from_arg("RELIANCE=22.04,HDFCBANK=17.14,ICICIBANK=12.62,INFY=10.86,TCS=9.20"))
        self.check_reel(size.size(w, v1()))

    def test_renormalised_weights(self):
        r = size.size(rows(TOP5), v1())
        shown = {p["ticker"]: round(p["weight"], 1) for p in r["positions"]}
        self.assertEqual(shown, {"RELIANCE": 30.7, "HDFCBANK": 23.9, "ICICIBANK": 17.6, "INFY": 15.1, "TCS": 12.8})

    def test_one_decimal_weights_stay_within_a_dollar(self):
        w = size.parse_weights({"RELIANCE": 30.7, "HDFCBANK": 23.9, "ICICIBANK": 17.6, "INFY": 15.1, "TCS": 12.8})
        r = size.size(w, v1())
        self.assertEqual(r["invested"], 4500)
        self.assertEqual(rupees(r)["RELIANCE"], 1250)
        for t, v in rupees(r).items():
            self.assertLessEqual(abs(v - REEL_V1[t]), 1.0, t)

    def test_orders_are_place_stock_order_shaped(self):
        r = size.size(rows(TOP5), v1())
        orders = size.orders_from(r, "a 13F")
        self.assertEqual(orders[0], {"symbol": "RELIANCE", "side": "buy", "notional": "1250", "type": "market",
                                     "time_in_force": "day", "why": orders[0]["why"]})
        self.assertIn("capped at 25%", orders[0]["why"])
        for o in orders:
            self.assertIsInstance(o["notional"], str)
            self.assertNotIn("qty", o)
        self.assertEqual([o["notional"] for o in orders], ["1250", "1119", "823", "708", "600"])

    def test_cents_mode_keeps_the_total(self):
        r = size.size(rows(TOP5), v1(), cents=True)
        d = rupees(r)
        self.assertEqual(d["RELIANCE"], 1250)
        self.assertAlmostEqual(sum(d.values()), 4500, places=2)
        self.assertAlmostEqual(d["HDFCBANK"], 1118.13, places=2)
        self.assertEqual(size.orders_from(r)[1]["notional"], "1118.13")

    def test_cap_redistributes_until_nobody_is_over(self):
        w = size.parse_weights({"A": 60, "B": 30, "C": 10})
        r = size.size(w, {"budget": 1000, "cash_buffer_pct": 0, "max_position_pct": 40, "min_order_inr": 1})
        self.assertEqual(rupees(r), {"A": 400, "B": 400, "C": 200})
        self.assertEqual(sorted(p["ticker"] for p in r["positions"] if p["capped"]), ["A", "B"])

    def test_everything_capped_leaves_money_idle(self):
        w = size.parse_weights({"RELIANCE": 50, "INFY": 50})
        r = size.size(w, v1())
        self.assertEqual(rupees(r), {"RELIANCE": 1250, "INFY": 1250})
        self.assertEqual(r["idle"], 2000)
        self.assertIn("every stock is at its cap", size.report(r, size.orders_from(r)))

    def test_slices_under_the_minimum_are_dropped_and_shared_out(self):
        w = size.parse_weights({"A": 90, "B": 7, "C": 3})
        r = size.size(w, {"budget": 100, "cash_buffer_pct": 10, "max_position_pct": 100, "min_order_inr": 5})
        self.assertNotIn("C", rupees(r))
        self.assertEqual(sum(rupees(r).values()), 90)
        self.assertTrue(all(v >= 5 for v in rupees(r).values()))
        self.assertEqual(r["dropped"][0]["ticker"], "C")

    def test_blocked_tickers_are_dropped_first(self):
        r = size.size(rows(TOP5), v1(blocked=["infy"]))
        self.assertNotIn("INFY", rupees(r))
        self.assertEqual(r["invested"], 4500)
        self.assertIn("blocked", r["dropped"][0]["reason"])

    def test_top_n(self):
        r = size.size(rows(TOP5), v1(max_position_pct=100), top=2)
        self.assertEqual(sorted(rupees(r)), ["HDFCBANK", "RELIANCE"])

    def test_whole_shares_need_prices(self):
        with self.assertRaises(size.SizeError):
            size.size(rows(TOP5), v1(fractional=False))
        with self.assertRaises(size.SizeError):
            size.size(rows(TOP5), cfg())          # the v2 example config is whole shares

    def test_whole_shares_with_prices(self):
        r = size.size(rows(TOP5), v1(fractional=False), prices=PRICES)
        self.assertTrue(r["whole_shares"])
        for p in r["positions"]:
            self.assertEqual(p["shares"], int(p["shares"]))
            self.assertAlmostEqual(p["rupees"], p["shares"] * PRICES[p["ticker"]], places=2)
            self.assertLessEqual(p["rupees"], 1250)
        self.assertAlmostEqual(r["invested"] + r["idle"], 4500, places=2)
        self.assertLess(r["idle"], min(PRICES.values()) * 2)
        orders = size.orders_from(r)
        self.assertTrue(all("qty" in o and "notional" not in o for o in orders))

    def test_no_budget_and_duplicates_are_errors(self):
        with self.assertRaises(size.SizeError):
            size.size(rows(TOP5), {"cash_buffer_pct": 10})
        with self.assertRaises(size.SizeError):
            size.size([{"ticker": "INFY", "name": "", "weight": 1}, {"ticker": "INFY", "name": "", "weight": 2}], v1())

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, "config.json")
            with open(c, "w") as fh:
                json.dump(v1(), fh)
            out = os.path.join(d, "trader", "orders.json")
            code, text, _ = run(["--targets", TARGETS, "--config", c, "--write", out])
            self.assertEqual(code, 0)
            self.assertIn("left idle", text)
            self.assertIn("require_stop", text)
            with open(out) as fh:
                doc = json.load(fh)
            self.assertEqual([o["symbol"] for o in doc["orders"]], ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS"])
            code, text, _ = run(["--targets", TARGETS, "--config", c, "--json"])
            self.assertEqual(json.loads(text)["result"]["idle"], 0)
            code, _, err = run(["--targets", "/nonexistent/targets.json", "--config", c])
            self.assertEqual(code, 1)
            self.assertIn("no weights file", err)


if __name__ == "__main__":
    unittest.main()
