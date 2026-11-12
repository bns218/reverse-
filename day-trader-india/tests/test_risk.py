"""trader-risk tests (India: NSE / BSE intraday).

tests/fixtures/trader-risk/orders-demo.json is exactly what trader-budget writes for the
demo plan: buy 159 DEMO, MIS, stop 358.30, target 370.10 (see test_budget.py)."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

check = load("trader-risk", "check")
ticket = load("trader-broker", "ticket")

CFG = os.path.join(ROOT, "trader-budget", "config.example.json")
ORDERS = os.path.join(FIX, "trader-risk", "orders-demo.json")
NOW = "2026-10-19 10:00"


def cfg(**over):
    with open(CFG) as fh:
        c = json.load(fh)
    c.update(over)
    return c


def demo(**over):
    with open(ORDERS) as fh:
        o = json.load(fh)["orders"][0]
    o = json.loads(json.dumps(o))
    for k, v in over.items():
        if v is None:
            o.pop(k, None)
        else:
            o[k] = v
    return o


def run_check(orders, c=None, now=NOW, **kw):
    return check.check(orders if isinstance(orders, list) else [orders], c or cfg(), now=check.parse_now(now), **kw)


def one(order, c=None, now=NOW, **kw):
    return run_check(order, c, now, **kw)["results"][0]


def reasons(r):
    return " | ".join(r["reasons"])


def placed(symbol="AAA", side="buy", max_loss=900.0, kind="entry", date="2026-10-19"):
    return {"symbol": symbol, "side": side, "status": "placed", "date": date, "kind": kind, "max_loss": max_loss}


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = check.main(argv)
    return code, out.getvalue(), err.getvalue()


class TheDemo(unittest.TestCase):
    def test_the_demo_order_passes_every_check(self):
        res = run_check(demo())
        r = res["results"][0]
        self.assertEqual((r["verdict"], r["kind"], r["reasons"]), ("PASS", "entry", []))
        self.assertEqual(r["value_inr"], 57904.62)
        self.assertEqual((r["entry_ref"], r["entry_ref_from"], r["stop"], r["target"]), (364.18, "plan", 358.3, 370.1))
        self.assertEqual((r["risk_per_share"], r["max_loss"], r["reward_risk"]), (5.88, 934.92, 1.01))
        self.assertEqual((res["pass"], res["block"]), (1, 0))
        self.assertEqual(res["now_ist"], "2026-10-19 10:00")
        self.assertEqual(res["cash_after"], 42095.38)
        self.assertIn("charges if it stops out (estimate) ₹60.80: ₹995.72 with the loss at the stop",
                      r["info"])
        self.assertNotIn("day_trades_5d", res["today"])           # no US pattern-day-trader rule here

    def test_seven_more_shares_break_the_max_loss(self):
        r = one(demo(qty="166", plan=dict(demo()["plan"], charges_at_stop=63.4)))
        self.assertEqual(r["verdict"], "BLOCK")
        self.assertEqual(len(r["reasons"]), 1)
        self.assertIn("loss: 166 shares x 5.88 risk a share = ₹976.08 at the stop plus ₹63.40 of charges "
                      "= ₹1,039.48, over your ₹1,000 max loss per trade", r["reasons"][0])
        # without the charge maths the bare loss is what counts
        self.assertEqual(one(demo(qty="166"), cfg(include_charges=False))["verdict"], "PASS")
        self.assertEqual(one(demo(qty="171"), cfg(include_charges=False))["verdict"], "BLOCK")

    def test_fingerprint_is_shared_with_the_broker(self):
        o = demo()
        self.assertEqual(check.fingerprint(o), ticket.fingerprint(o))
        self.assertEqual(check.ORDER_FIELDS, ticket.ORDER_FIELDS)
        self.assertNotEqual(check.fingerprint(o), check.fingerprint(demo(qty="160")))
        self.assertNotEqual(check.fingerprint(o), check.fingerprint(demo(product="CNC")))   # the product is part of it
        self.assertEqual(check.fingerprint(o), check.fingerprint(demo(why="other words")))

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "state", "risk.json")
            code, text, err = run(["--orders", ORDERS, "--config", CFG, "--portfolio", os.path.join(d, "none"),
                                   "--prices", os.path.join(d, "none"), "--state", os.path.join(d, "none"),
                                   "--now", NOW, "--out", out])
            self.assertEqual(code, 0, err)
            self.assertIn("PASS  #1 buy DEMO 159 shares, entry", text)
            self.assertIn("max loss ₹934.92 (limit ₹1,000), reward:risk 1.01 (min 1)", text)
            self.assertIn("1 passed, 0 blocked at 2026-10-19 10:00 IST", text)
            self.assertIn("paper account", text)
            self.assertNotIn(chr(36), text)
            with open(out) as fh:
                rec = json.load(fh)
            self.assertEqual(rec["results"][0]["fingerprint"], check.fingerprint(demo()))
            self.assertEqual(rec["orders_file"], ORDERS)
            code, text, _ = run(["--orders", ORDERS, "--config", CFG, "--portfolio", os.path.join(d, "none"),
                                 "--now", "2026-10-19 15:00", "--no-write", "--json"])
            self.assertEqual(code, 1)
            self.assertIn("no new entries after 14:45 IST", json.loads(text)["results"][0]["reasons"][0])
            code, _, err = run(["--orders", os.path.join(d, "nope.json")])
            self.assertEqual(code, 1)
            self.assertIn("no orders file", err)
            self.assertNotIn("Traceback", err)


class Format(unittest.TestCase):
    def test_whole_shares_no_notional(self):
        r = one(demo(qty=None, notional="50000"))
        self.assertIn("whole shares only: give a qty, not a notional (rupee) amount", reasons(r))
        self.assertIn("whole shares only on NSE and BSE", reasons(one(demo(qty="10.5"))))
        self.assertIn("exactly one of qty or notional", reasons(one(demo(qty=None))))

    def test_exchange_and_product(self):
        self.assertIn("exchange must be NSE or BSE", reasons(one(demo(exchange="NYSE"))))
        self.assertIn("product must be MIS", reasons(one(demo(product="BO"))))
        self.assertEqual(one(demo(exchange="BSE"))["verdict"], "PASS")
        r = one(demo(product="CNC"))
        self.assertEqual(r["verdict"], "PASS")
        self.assertTrue(any("delivery order, not intraday" in w for w in r["warnings"]))
        # an order without the fields falls back to the config (NSE, MIS)
        self.assertEqual(one(demo(exchange=None, product=None))["verdict"], "PASS")

    def test_order_shape(self):
        self.assertIn("side must be buy or sell", reasons(one(demo(side="hold"))))
        self.assertIn("no symbol", reasons(one(demo(symbol=""))))
        self.assertIn("unknown order type", reasons(one(demo(type="iceberg"))))
        self.assertIn("needs a limit_price", reasons(one(demo(type="limit"))))
        self.assertIn("needs time_in_force day", reasons(one(demo(time_in_force="gtc"))))
        self.assertIn("needs both take_profit_limit_price and stop_loss_stop_price",
                      reasons(one(demo(take_profit_limit_price=None))))
        self.assertIn("no extended-hours trading", reasons(one(demo(extended_hours=True))))
        self.assertIn("must be a positive number", reasons(one(demo(stop_loss_stop_price="-1"))))
        r = one(demo(qty=159))
        self.assertTrue(any("send qty as a string" in w for w in r["warnings"]))

    def test_assets(self):
        for sym in ("RELIANCE", "M&M", "BAJAJ-AUTO", "3MINDIA", "NIFTYBEES"):
            r = one(demo(symbol=sym))
            self.assertNotIn("asset:", reasons(r), sym)
        for sym in ("NIFTY26OCTFUT", "RELIANCE26OCT1400CE", "BANKNIFTY26OCT52000PE", "NIFTY2611324500PE"):
            self.assertIn("is a futures or options (F&O) contract; F&O is off", reasons(one(demo(symbol=sym))), sym)
            r = one(demo(symbol=sym), cfg(allow_options=True))
            self.assertNotIn("asset:", reasons(r), sym)
            self.assertTrue(any("F&O order" in w for w in r["warnings"]))
        for sym in ("BTC/INR", "RELIANCE.NS", "TOOLONGSYMBOLNAMEFORNSE"):
            self.assertIn("does not look like an NSE or BSE equity symbol", reasons(one(demo(symbol=sym))), sym)


class Limits(unittest.TestCase):
    def test_blocked_list_holds_t2t_and_surveillance_names(self):
        r = one(demo(), cfg(blocked=["demo"]))
        self.assertIn("blocked: DEMO is on your blocked list", reasons(r))

    def test_max_and_min_order(self):
        self.assertIn("is over your ₹50,000 max order", reasons(one(demo(), cfg(max_order_inr=50000))))
        small = demo(qty="1")
        self.assertIn("₹364.18 is under your ₹500 minimum order", reasons(one(small)))

    def test_position_cap_and_cash_buffer(self):
        self.assertIn("position: DEMO would be ₹57,904.62, 57.9% of the ₹100,000 account, over your 50% cap",
                      reasons(one(demo(), cfg(max_position_pct=50))))
        pf = {"cash": 60000, "positions": []}
        r = one(demo(), portfolio=pf)
        self.assertIn("cash: leaves ₹2,095.38 cash, under your 10% buffer of ₹6,000", reasons(r))
        r = one(demo(), portfolio={"cash": 50000, "positions": []})
        self.assertIn("cash: needs ₹57,904.62 but only ₹50,000 cash; that would be margin", reasons(r))
        self.assertIn("Intraday leverage is off", reasons(r))

    def test_intraday_leverage(self):
        pf = {"cash": 20000, "positions": []}
        lev = cfg(allow_margin=True, intraday_leverage=5, max_position_pct=500)
        res = run_check(demo(), lev, portfolio=pf)
        r = res["results"][0]
        self.assertEqual(r["verdict"], "PASS", r["reasons"])
        self.assertTrue(any("intraday leverage 5x: about ₹11,580.92 margin" in i for i in r["info"]))
        self.assertEqual(res["cash_after"], 8419.08)                # only the margin leaves the cash
        # leverage never applies to a delivery (CNC) order
        r = one(demo(product="CNC"), lev, portfolio=pf)
        self.assertIn("cash: needs ₹57,904.62", reasons(r))
        # set but not allowed: ignored
        r = one(demo(), cfg(intraday_leverage=5), portfolio=pf)
        self.assertIn("cash: needs ₹57,904.62", reasons(r))
        with self.assertRaises(check.RiskError):
            run_check(demo(), cfg(allow_margin=True, intraday_leverage=8))

    def test_duplicates_and_the_daily_order_limit(self):
        res = run_check([demo(), demo()])
        self.assertEqual([r["verdict"] for r in res["results"]], ["PASS", "BLOCK"])
        self.assertIn("duplicate: a second buy DEMO in this batch", reasons(res["results"][1]))
        r = one(demo(), state={"orders": [placed("DEMO")]})
        self.assertIn("duplicate: a buy DEMO was already placed today", reasons(r))
        state = {"orders": [placed("S%d" % i, max_loss=1.0, kind="exit", side="sell") for i in range(10)]}
        self.assertIn("daily limit: 10 placed today", reasons(one(demo(), state=state)))

    def test_short_sales_are_off(self):
        r = one(demo(side="sell", stop_loss_stop_price="370.10", take_profit_limit_price="358.30"))
        self.assertIn("short: selling more DEMO than you hold (0 shares); short selling is off", reasons(r))


class DayTradeChecks(unittest.TestCase):
    def test_a_stop_is_required(self):
        o = demo(order_class=None, stop_loss_stop_price=None, take_profit_limit_price=None)
        o["plan"] = {"entry": 364.18, "target": 370.1}
        self.assertIn("stop: no stop", reasons(one(o)))
        r = one(o, cfg(require_stop=False))
        self.assertEqual(r["verdict"], "PASS")
        self.assertTrue(any("no stop: the max loss is not capped" in w for w in r["warnings"]))

    def test_a_plan_stop_counts_but_warns(self):
        o = demo(order_class=None, stop_loss_stop_price=None, take_profit_limit_price=None)
        r = one(o)
        self.assertEqual((r["verdict"], r["stop"], r["max_loss"]), ("PASS", 358.3, 934.92))
        self.assertTrue(any("in the plan only, not at the broker" in w for w in r["warnings"]))

    def test_stop_and_target_on_the_right_side(self):
        self.assertIn("stop: the stop 365.00 must be below the entry 364.18",
                      reasons(one(demo(stop_loss_stop_price="365.00"))))
        self.assertIn("target: the target 364.00 must be above the entry 364.18",
                      reasons(one(demo(take_profit_limit_price="364.00"))))

    def test_reward_risk(self):
        r = one(demo(take_profit_limit_price="368.00"))
        self.assertIn("reward:risk: 0.65 (target 368.00, entry 364.18, stop 358.30) is under your minimum 1",
                      reasons(r))
        self.assertEqual(one(demo(take_profit_limit_price="368.00"), cfg(min_reward_risk=0.5))["verdict"], "PASS")

    def test_a_fresh_higher_price_is_the_entry(self):
        now = check.parse_now(NOW)
        r = one(demo(), cfg(min_reward_risk=0), prices={"DEMO": 366.475}, price_times={"DEMO": now})
        self.assertEqual((r["entry_ref"], r["entry_ref_from"], r["risk_per_share"]), (366.48, "price", 8.18))
        self.assertIn("loss: 159 shares x 8.18 risk a share", reasons(r))
        # a lower price does not shrink the risk; a stale one is not used
        r = one(demo(), prices={"DEMO": 363.0}, price_times={"DEMO": now})
        self.assertEqual((r["entry_ref"], r["entry_ref_from"]), (364.18, "plan"))
        old = now - check.datetime.timedelta(minutes=40)
        r = one(demo(), prices={"DEMO": 366.475}, price_times={"DEMO": old})
        self.assertEqual((r["verdict"], r["entry_ref"]), ("PASS", 364.18))
        self.assertTrue(any("older than 15 minutes" in w for w in r["warnings"]))

    def test_a_limit_order_uses_its_limit_price(self):
        r = one(demo(type="limit", limit_price="364.00"))
        self.assertEqual((r["entry_ref"], r["entry_ref_from"], r["risk_per_share"]), (364.0, "limit", 5.7))

    def test_daily_loss_and_trades_per_day(self):
        state = {"orders": [placed("AAA", max_loss=950.0), placed("BBB", max_loss=950.0),
                            placed("OLD", max_loss=999.0, date="2026-10-16")]}
        res = run_check(demo(), state=state)
        r = res["results"][0]
        self.assertEqual(r["verdict"], "PASS")                      # 1,900 + 934.92 is under 3,000
        self.assertIn("today before this: 2 of 3 trades, ₹1,900 of ₹3,000 daily loss", r["info"])
        state["orders"].append(placed("CCC", max_loss=200.0))
        r = one(demo(), state=state)
        self.assertIn("daily loss: ₹2,100 already at risk today plus ₹934.92 for this one = ₹3,034.92, "
                      "over your ₹3,000 daily loss limit", reasons(r))
        self.assertIn("trades: 3 entries placed today", reasons(r))
        # exits do not count as trades
        state = {"orders": [placed("S%d" % i, side="sell", kind="exit", max_loss=None) for i in range(4)]}
        self.assertEqual(one(demo(), state=state)["verdict"], "PASS")

    def test_the_batch_counts_toward_the_daily_limits(self):
        orders = [demo(symbol=s) for s in ("AAA", "BBB", "CCC", "DDD")]
        res = run_check(orders, cfg(max_position_pct=100, cash_buffer_pct=0, budget=400000))
        self.assertEqual([r["verdict"] for r in res["results"]], ["PASS", "PASS", "PASS", "BLOCK"])
        last = reasons(res["results"][3])
        self.assertIn("daily loss:", last)
        self.assertIn("trades: 0 entries placed today plus 3 passed earlier in this batch", last)

    def test_entry_window_ist(self):
        self.assertIn("window: no new entries before 09:30 IST (it is 09:20)",
                      reasons(one(demo(), now="2026-10-19 09:20")))
        self.assertEqual(one(demo(), now="2026-10-19 14:45")["verdict"], "PASS")
        self.assertIn("window: no new entries after 14:45 IST (it is 14:46)",
                      reasons(one(demo(), now="2026-10-19 14:46")))
        self.assertIn("the market is closed (Mon 2026-10-19 09:10 IST; the session is 09:15 to 15:30)",
                      reasons(one(demo(), now="2026-10-19 09:10")))
        self.assertIn("the market is closed", reasons(one(demo(), now="2026-10-19 15:30")))
        self.assertIn("window: the market is closed today (weekend", reasons(one(demo(), now="2026-10-17 10:00")))
        self.assertIn("NSE holiday: Dussehra", reasons(one(demo(), now="2026-10-20 10:00")))
        self.assertEqual(one(demo(), now="2026-11-26 10:00")["verdict"], "PASS")   # US Thanksgiving: NSE is open
        # the window is IST whatever the machine's clock says: 04:30 UTC is 10:00 IST
        self.assertEqual(one(demo(), now="2026-10-19T04:30:00Z")["verdict"], "PASS")
        self.assertIn("window:", reasons(one(demo(), now="2026-10-19T10:00:00Z")))   # 15:30 IST
        # the window can be switched off
        off = cfg(no_entries_before=None, no_entries_after=None)
        self.assertEqual(one(demo(), off, now="2026-10-17 03:00")["verdict"], "PASS")

    def test_holidays_from_the_config_and_unknown_years(self):
        try:
            r = one(demo(), cfg(extra_holidays=["2026-12-31"]), now="2026-12-31 10:00")
            self.assertIn("holiday from your config", reasons(r))
        finally:
            check.NSE_HOLIDAYS.pop("2026-12-31", None)
        res = run_check(demo(), now="2027-03-01 10:00")
        self.assertTrue(any("holiday list covers 2026 only" in w and "extra_holidays" in w for w in res["warnings"]))

    def test_circuit_limits(self):
        # no band known: the rule is silent
        self.assertEqual(one(demo(), prev_closes={"DEMO": 354.72})["verdict"], "PASS")
        # a 5% band on yesterday's 354.72: 336.98 to 372.46. Entry 364.18 is 2.2% under the top: fine
        c5 = cfg(price_band_pct=5)
        r = one(demo(), c5, prev_closes={"DEMO": 354.72})
        self.assertEqual(r["verdict"], "PASS")
        self.assertIn("price band 5%: 336.98 to 372.46 today", r["info"])
        # a 3% band tops out at 365.36: the entry is inside the last 1%
        r = one(demo(), cfg(price_bands={"DEMO": 3}), prev_closes={"DEMO": 354.72})
        self.assertIn("circuit: entry 364.18 is within 1% of the upper circuit 365.36 (3% band on yesterday's "
                      "close 354.72): trading can freeze there", reasons(r))
        # a stop under the lower circuit cannot fill
        o = demo(stop_loss_stop_price="336.00", qty="20", plan={"entry": 364.18, "stop": 336.0, "target": 395.0},
                 take_profit_limit_price="395.00")
        r = one(o, c5, prev_closes={"DEMO": 354.72})
        self.assertIn("circuit: the stop 336.00 is at or under the lower circuit 336.98", reasons(r))
        # the per-symbol band wins over the default
        r = one(demo(), cfg(price_band_pct=3, price_bands={"DEMO": 20}), prev_closes={"DEMO": 354.72})
        self.assertEqual(r["verdict"], "PASS")

    def test_prev_close_comes_from_the_prices_file(self):
        with tempfile.TemporaryDirectory() as d:
            pp = os.path.join(d, "prices.json")
            with open(pp, "w") as fh:
                json.dump({"as_of": "2026-10-19T04:29:00Z", "prices": {"DEMO": 364.1},
                           "detail": {"DEMO": {"prev_close": 354.72, "time": "2026-10-19T04:29:00Z"}}}, fh)
            c = os.path.join(d, "config.json")
            with open(c, "w") as fh:
                json.dump(cfg(price_band_pct=3), fh)
            code, text, _ = run(["--orders", ORDERS, "--config", c, "--portfolio", os.path.join(d, "none"),
                                 "--prices", pp, "--state", os.path.join(d, "none"), "--now", NOW, "--no-write"])
            self.assertEqual(code, 1)
            self.assertIn("upper circuit 365.36", text)


class Exits(unittest.TestCase):
    PF = {"cash": 5000, "positions": [{"ticker": "DEMO", "shares": 159}]}

    def test_getting_out_is_never_blocked_by_the_entry_rules(self):
        sell = {"symbol": "DEMO", "exchange": "NSE", "product": "MIS", "side": "sell", "qty": "159",
                "type": "market", "time_in_force": "day"}
        r = one(sell, cfg(blocked=["DEMO"], max_order_inr=1000), now="2026-10-19 15:10",
                portfolio=self.PF, prices={"DEMO": 360.0})
        self.assertEqual((r["verdict"], r["kind"]), ("PASS", "exit"))
        self.assertTrue(any(w.startswith("exit, not blocked: blocked:") for w in r["warnings"]))
        self.assertTrue(any(w.startswith("exit, not blocked: size:") for w in r["warnings"]))
        # selling more than you hold is a short, and that is blocked
        r = one(dict(sell, qty="200"), portfolio=self.PF, prices={"DEMO": 360.0})
        self.assertIn("short: selling more DEMO than you hold (159 shares)", reasons(r))

    def test_buy_then_sell_in_one_batch(self):
        sell = {"symbol": "DEMO", "exchange": "NSE", "product": "MIS", "side": "sell", "qty": "159",
                "type": "market", "time_in_force": "day"}
        res = run_check([demo(), sell], prices={"DEMO": 364.18})
        self.assertEqual([(r["verdict"], r["kind"]) for r in res["results"]], [("PASS", "entry"), ("PASS", "exit")])
        self.assertEqual(res["cash_after"], 100000.0)


class SkillDoc(unittest.TestCase):
    def test_skill_md(self):
        with open(os.path.join(ROOT, "trader-risk", "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith("---\nname: trader-risk\n"))
        low = " ".join(text.lower().split())
        for must in ("pass", "block", "max_loss_per_trade_inr", "circuit", "mis", "14:45", "whole shares",
                     "not financial advice", "## safety"):
            self.assertIn(must, low)
        for never in ("pdt_guard", "alpaca", "new york", chr(36)):
            self.assertNotIn(never, low)


if __name__ == "__main__":
    unittest.main()
