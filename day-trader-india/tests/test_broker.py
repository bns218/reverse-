"""trader-broker tests (India). The order under test is the one trader-budget writes for the
demo plan: buy 159 DEMO on NSE, MIS, stop 358.30, target 370.10."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX

ticket = load("trader-broker", "ticket")
check = load("trader-risk", "check")

CFG_PATH = os.path.join(ROOT, "trader-budget", "config.example.json")
ORDERS_PATH = os.path.join(FIX, "trader-risk", "orders-demo.json")
PLAN_PATH = os.path.join(FIX, "trader-budget", "plan-demo.json")
NOW = "2026-10-19 10:00"
TODAY = "2026-10-19"
SELL = {"symbol": "INFY", "exchange": "NSE", "product": "MIS", "side": "sell", "qty": "3", "type": "market",
        "time_in_force": "day"}
BATCH = ["INFY", "RELIANCE", "TCS"]
DEMO_ORDER = {"symbol": "DEMO", "exchange": "NSE", "product": "MIS", "side": "buy", "qty": "159", "type": "market",
              "time_in_force": "day", "order_class": "bracket", "take_profit_limit_price": "370.10",
              "stop_loss_stop_price": "358.30"}
DEMO_PLAIN = ("BUY 159 DEMO on NSE, intraday (MIS), market, good for today / stop-loss 358.30 / target 370.10 / "
              "max loss about ₹934.92 if the stop fills at 358.30, plus about ₹60.80 of charges (it can fill "
              "worse in a fast market, or not at all at a circuit limit)")
BASE = {"variety": "regular", "exchange": "NSE", "tradingsymbol": "DEMO", "product": "MIS", "validity": "DAY"}
KITE_ENTRY = dict(BASE, transaction_type="BUY", quantity=159, order_type="MARKET")
KITE_STOP = dict(BASE, transaction_type="SELL", quantity=159, order_type="SL-M", trigger_price=358.3)


def demo(**over):
    with open(ORDERS_PATH) as fh:
        o = json.load(fh)["orders"][0]
    o.update(over)
    return o


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = ticket.main(argv)
    return code, out.getvalue(), err.getvalue()


class ExplicitYes(unittest.TestCase):
    def yes(self, reply, order=SELL, batch=BATCH):
        return ticket.parse_yes(reply, order, batch)[0]

    def test_plain_yes_counts(self):
        for r in ("yes", "Yes.", "YES", "y", "yes place it", "Yes, sell it", "yes INFY", "yes sell 3 INFY", "yes 3"):
            self.assertTrue(self.yes(r), r)

    def test_anything_else_does_not(self):
        for r in ("", "sure", "ok", "okay", "go", "do it", "yeah", "yep", "haan", "absolutely", "send it",
                  "yes to all", "yes, all of them", "yes to the rest", "yes both",
                  "yes RELIANCE", "yes 4", "yes but make it 5", "yes?", "no", "not yes",
                  "yes, wait", "yes if it is under 1400"):
            self.assertFalse(self.yes(r), r)

    def test_a_yes_for_the_demo_order(self):
        o = demo()
        for r in ("yes", "yes 159 DEMO", "yes 358.30", "yes max loss 934.92", "yes target 370.10"):
            self.assertTrue(self.yes(r, o, ["DEMO"]), r)
        for r in ("yes 160", "yes 200 DEMO", "yes but stop at 357", "yes, stop 358.30", "yes INFY", "sure"):
            self.assertFalse(self.yes(r, o, ["DEMO", "INFY"]), r)

    def test_long_nse_symbols_and_symbols_with_digits(self):
        m = dict(SELL, symbol="M&M")
        self.assertTrue(self.yes("yes sell 3 M&M", m, ["M&M", "BAJAJ-AUTO", "RELIANCE"]))
        self.assertFalse(self.yes("yes BAJAJ-AUTO", m, ["M&M", "BAJAJ-AUTO", "RELIANCE"]))
        self.assertFalse(self.yes("yes RELIANCE", m, ["M&M", "BAJAJ-AUTO", "RELIANCE"]))
        three = dict(SELL, symbol="3MINDIA", qty="2")
        self.assertTrue(self.yes("yes 3MINDIA", three, ["3MINDIA"]))       # the 3 is part of the name
        self.assertTrue(self.yes("yes sell 2 3MINDIA", three, ["3MINDIA"]))
        self.assertFalse(self.yes("yes sell 3 3MINDIA", three, ["3MINDIA"]))


class TicketShape(unittest.TestCase):
    def test_tool_input_leaves_out_why_and_plan(self):
        self.assertEqual(ticket.tool_input(demo()), DEMO_ORDER)
        self.assertEqual(ticket.fingerprint(demo()), ticket.fingerprint(DEMO_ORDER))
        self.assertEqual(ticket.tool_input(dict(SELL, qty=3, why="x")), SELL)      # numbers become strings

    def test_kite_calls_entry_then_stop_and_no_target_order(self):
        calls = ticket.kite_calls(demo())
        self.assertEqual([c["tool"] for c in calls], ["place_order", "place_order"])
        self.assertEqual(calls[0]["arguments"], KITE_ENTRY)
        self.assertEqual(calls[1]["arguments"], KITE_STOP)
        self.assertIn("only after the entry has filled", calls[1]["step"])
        # the target goes to the broker only when you ask for it
        calls = ticket.kite_calls(demo(), {"target_order": "limit"})
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[2]["arguments"], dict(BASE, transaction_type="SELL", quantity=159, order_type="LIMIT",
                                                     price=370.1))
        self.assertIn("cancel it the moment the stop fills", calls[2]["step"])

    def test_kite_calls_for_other_orders(self):
        lim = ticket.kite_calls(demo(type="limit", limit_price="364.00"))[0]["arguments"]
        self.assertEqual((lim["order_type"], lim["price"]), ("LIMIT", 364))
        self.assertEqual(ticket.kite_calls(SELL), [{"step": "entry", "tool": "place_order", "arguments": {
            "variety": "regular", "exchange": "NSE", "tradingsymbol": "INFY", "product": "MIS", "validity": "DAY",
            "transaction_type": "SELL", "quantity": 3, "order_type": "MARKET"}}])
        bse = ticket.kite_calls(dict(SELL, exchange="BSE", product="CNC"))[0]["arguments"]
        self.assertEqual((bse["exchange"], bse["product"]), ("BSE", "CNC"))
        sl = ticket.kite_calls(demo(stop_loss_limit_price="358.00"))[1]["arguments"]
        self.assertEqual((sl["order_type"], sl["trigger_price"], sl["price"]), ("SL", 358.3, 358))

    def test_plain_english(self):
        self.assertEqual(ticket.plain(SELL), "SELL 3 shares of INFY on NSE, intraday (MIS), market order, "
                                             "good for today")
        self.assertEqual(ticket.plain(dict(SELL, qty="1", type="limit", limit_price="1495", product="CNC")),
                         "SELL 1 share of INFY on NSE, delivery (CNC), limit order at ₹1,495, good for today")
        self.assertEqual(ticket.plain(demo()), DEMO_PLAIN)
        lim = demo(type="limit", limit_price="364.00")
        self.assertEqual(ticket.plain(lim).split(" / ")[0],
                         "BUY 159 DEMO on NSE, intraday (MIS), limit 364.00, good for today")
        self.assertEqual(ticket.max_loss(lim), (906.3, 358.3))
        self.assertEqual(ticket.max_loss(dict(DEMO_ORDER)), (None, 358.3))
        self.assertEqual(ticket.ny_iso(ticket.parse_now(NOW)), "2026-10-19T10:00:00+05:30")


class DesktopConfig(unittest.TestCase):
    def test_example_is_the_hosted_kite_server_with_no_keys(self):
        with open(os.path.join(ROOT, "trader-broker", "claude_desktop_config.example.json")) as fh:
            text = fh.read()
        server = json.loads(text)["mcpServers"]["kite"]
        self.assertEqual((server["command"], server["args"]), ("npx", ["mcp-remote", "https://mcp.kite.trade/mcp"]))
        self.assertNotIn("env", server)                 # Kite logs in through the browser: no keys in a file
        self.assertNotIn("KEY", text.upper().replace("KITE", ""))


class Flow(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.orders = os.path.join(self.d, "orders.json")
        shutil.copy(ORDERS_PATH, self.orders)
        self.cfg = os.path.join(self.d, "config.json")
        shutil.copy(CFG_PATH, self.cfg)
        self.risk = os.path.join(self.d, "state", "risk.json")
        self.state = os.path.join(self.d, "state", "broker.json")
        self.pf = os.path.join(self.d, "portfolio.json")
        self.none = os.path.join(self.d, "none")

    def tearDown(self):
        shutil.rmtree(self.d)

    def args(self, *extra, **kw):
        return list(extra) + ["--orders", self.orders, "--config", self.cfg, "--risk", self.risk,
                              "--state", self.state, "--now", kw.get("now", NOW)]

    def set_cfg(self, **over):
        with open(self.cfg) as fh:
            c = json.load(fh)
        c.update(over)
        with open(self.cfg, "w") as fh:
            json.dump(c, fh)

    def run_risk(self, now=NOW):
        with redirect_stdout(io.StringIO()):
            return check.main(["--orders", self.orders, "--config", self.cfg, "--portfolio", self.pf,
                               "--prices", self.none, "--state", self.state, "--now", now, "--out", self.risk])

    def state_doc(self):
        with open(self.state) as fh:
            return json.load(fh)

    def test_nothing_is_ready_before_the_risk_check(self):
        code, text, _ = run(self.args("show"))
        self.assertEqual(code, 1)
        self.assertIn("NOT READY", text)
        self.assertNotIn("Reply \"yes\"", text)
        code, _, err = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 1)
        self.assertIn("not ready", err)

    def test_the_paper_flow_calls_no_broker(self):
        self.assertEqual(self.run_risk(), 0)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertEqual(code, 0)
        self.assertIn("ORDER 1 of 1, PAPER (simulated, nothing is sent to a broker), Zerodha Kite", text)
        for part in DEMO_PLAIN.split(" / "):
            self.assertIn("  " + part + "\n", text)
        self.assertIn("READY: trader-risk PASS", text)
        self.assertIn("Paper mode: no broker is called", text)
        self.assertIn('Reply "yes" to paper trade this one order', text)
        self.assertNotIn("place_order", text)
        self.assertNotIn("Allow once", text)
        self.assertNotIn(chr(36), text)
        tj = json.loads(run(self.args("show", "--index", "1", "--json"))[1])
        tj = tj[0] if isinstance(tj, list) else tj
        self.assertEqual((tj["tool"], tj["broker_calls"], tj["tool_input"]), (None, [], DEMO_ORDER))

        code, text, _ = run(self.args("approve", "--index", "1", "--reply", "sure"))
        self.assertEqual(code, 1)
        self.assertIn("Not recorded", text)
        self.assertFalse(os.path.exists(self.state))

        code, text, _ = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 0)
        self.assertIn("ticket.py result --index 1 --status placed --broker-id PAPER", text)
        code, _, err = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 1)
        self.assertIn("APPROVED", err)

        code, text, _ = run(self.args("result", "--index", "1", "--status", "placed", "--broker-id", "PAPER",
                                      "--filled-qty", "159", "--filled-price", "364.20", "--portfolio", self.pf,
                                      now="2026-10-19 10:01"))
        self.assertEqual(code, 0)
        st = self.state_doc()
        self.assertEqual([r["status"] for r in st["orders"]], ["approved", "placed", "filled"])
        appr, plc = st["orders"][0], st["orders"][1]
        self.assertEqual((appr["reply"], appr["kind"], appr["max_loss"], appr["date"]),
                         ("yes", "entry", 934.92, TODAY))
        self.assertEqual(appr["at"], "2026-10-19T10:00:00+05:30")
        self.assertEqual((appr["paper"], appr["broker"]), (True, "zerodha"))
        self.assertEqual((plc["broker_order_id"], plc["max_loss"], plc["kind"]), ("PAPER", 934.92, "entry"))
        with open(self.pf) as fh:
            pf = json.load(fh)
        self.assertEqual(pf["cash"], 42092.2)                # 100,000 - 159 x 364.20
        self.assertEqual(pf["positions"][0]["shares"], 159)

        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("DONE: placed", text)
        code, text, _ = run(["log", "--state", self.state, "--now", NOW])
        self.assertIn("1 placed today", text)
        self.assertIn("max loss ₹934.92", text)

        # trader-risk now counts it: a second DEMO buy today is a duplicate, and 934.92 is used
        res = check.check([demo()], {"budget": 100000}, state=st, now=check.parse_now("2026-10-19 10:15"))
        self.assertIn("already placed today", " ".join(res["results"][0]["reasons"]))
        self.assertEqual((res["today"]["entries_placed"], res["today"]["loss_at_risk"]), (1, 934.92))

    def test_a_live_zerodha_ticket_shows_the_kite_calls(self):
        self.set_cfg(paper=False)
        self.assertEqual(self.run_risk(), 0)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertEqual(code, 0)
        self.assertIn("ORDER 1 of 1, LIVE ACCOUNT, REAL MONEY, Zerodha Kite", text)
        self.assertIn("Claude will call the Kite connector's place_order tool, 2 calls, with exactly:", text)
        self.assertIn('"order_type": "SL-M"', text)
        self.assertIn('"trigger_price": 358.3', text)
        self.assertIn("The target 370.10 is NOT sent as an order", text)
        self.assertIn("would open a short", text)
        self.assertIn("Allow once", text)
        self.assertNotIn('"plan"', text)
        tj = json.loads(run(self.args("show", "--index", "1", "--json"))[1])
        tj = tj[0] if isinstance(tj, list) else tj
        self.assertEqual([c["arguments"] for c in tj["broker_calls"]], [KITE_ENTRY, KITE_STOP])
        code, text, _ = run(self.args("approve", "--index", "1", "--reply", "yes"))
        self.assertEqual(code, 0)
        self.assertIn('"transaction_type": "BUY"', text)
        self.assertIn("ticket.py result --index 1 --status placed|denied|failed", text)
        self.assertFalse(self.state_doc()["orders"][0]["paper"])

    def test_another_broker_gets_the_neutral_order(self):
        self.set_cfg(paper=False, broker="upstox")
        self.run_risk()
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("LIVE ACCOUNT, REAL MONEY, Upstox", text)
        self.assertIn("Use your Upstox connector's order tool with these details", text)
        self.assertIn('"stop_loss_stop_price": "358.30"', text)
        self.assertNotIn("tradingsymbol", text)

    def test_flatten_before_the_square_off(self):
        self.run_risk()
        run(self.args("approve", "--index", "1", "--reply", "yes"))
        run(self.args("result", "--index", "1", "--status", "placed", "--broker-id", "PAPER",
                      "--filled-qty", "159", "--filled-price", "364.20", "--portfolio", self.pf))
        late = "2026-10-19 15:15"
        code, text, _ = run(["flatten", "--symbol", "DEMO", "--orders", self.orders, "--portfolio", self.pf,
                             "--plan", PLAN_PATH, "--config", self.cfg, "--now", late])
        self.assertEqual(code, 0)
        self.assertIn("SELL 159 shares of DEMO on NSE, intraday (MIS), market order, good for today "
                      "(flat by 15:15 IST)", text)
        self.assertIn("replaced 1 earlier proposal", text)
        self.assertIn("CANCEL IT FIRST", text)
        self.assertIn("around 15:20", text)
        with open(self.orders) as fh:
            doc = json.load(fh)
        self.assertEqual(ticket.tool_input(doc["orders"][0]),
                         {"symbol": "DEMO", "exchange": "NSE", "product": "MIS", "side": "sell", "qty": "159",
                          "type": "market", "time_in_force": "day"})
        self.assertEqual(self.run_risk(now=late), 0)       # after the 14:45 entry cutoff: an exit still passes
        with open(self.risk) as fh:
            self.assertEqual(json.load(fh)["results"][0]["kind"], "exit")
        code, text, _ = run(self.args("show", now=late))
        self.assertEqual(code, 0)
        self.assertIn("READY", text)
        self.assertEqual(run(self.args("approve", "--index", "1", "--reply", "yes sell 159 DEMO", now=late))[0], 0)
        code, _, _ = run(self.args("result", "--index", "1", "--status", "placed", "--filled-qty", "159",
                                   "--filled-price", "366.10", "--portfolio", self.pf, now="2026-10-19 15:16"))
        self.assertEqual(code, 0)
        with open(self.pf) as fh:
            pf = json.load(fh)
        self.assertEqual((pf["cash"], pf["positions"]), (100302.1, []))
        code, _, err = run(["flatten", "--symbol", "DEMO", "--orders", self.orders, "--portfolio", self.pf,
                            "--now", late])
        self.assertEqual(code, 1)
        self.assertIn("nothing to flatten", err)

    def test_flatten_with_the_broker_qty(self):
        code, text, _ = run(["flatten", "--symbol", "demo", "--qty", "159", "--orders", self.orders,
                             "--portfolio", self.none, "--plan", self.none, "--config", self.cfg, "--now", NOW])
        self.assertEqual(code, 0)
        self.assertIn("flat by 15:15 IST", text)
        self.assertNotIn("Check it against the broker's get_positions", text)
        self.assertEqual(run(["flatten", "--symbol", "DEMO", "--qty", "0", "--orders", self.orders])[0], 1)

    def test_an_edited_order_is_not_ready(self):
        self.run_risk()
        with open(self.orders) as fh:
            doc = json.load(fh)
        doc["orders"][0]["qty"] = "160"
        with open(self.orders, "w") as fh:
            json.dump(doc, fh)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertEqual(code, 1)
        self.assertIn("was not in the last risk check", text)

    def test_yesterdays_check_does_not_count(self):
        self.run_risk(now="2026-10-16 10:00")
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("not today", text)

    def test_blocked_orders_are_never_ready(self):
        self.assertEqual(self.run_risk(now="2026-10-19 09:20"), 1)
        code, text, _ = run(self.args("show", "--index", "1", now="2026-10-19 09:20"))
        self.assertIn("BLOCKED by trader-risk: window: no new entries before 09:30", text)
        code, _, _ = run(self.args("approve", "--index", "1", "--reply", "yes", now="2026-10-19 09:20"))
        self.assertEqual(code, 1)

    def test_result_needs_an_approval_and_decline_is_logged(self):
        self.run_risk()
        code, _, err = run(self.args("result", "--index", "1", "--status", "placed"))
        self.assertEqual(code, 1)
        self.assertIn("no yes recorded", err)
        code, text, _ = run(self.args("decline", "--index", "1", "--reply", "no thanks"))
        self.assertEqual(code, 0)
        code, text, _ = run(self.args("show", "--index", "1"))
        self.assertIn("DONE: declined", text)

    def test_fill_sell_relieves_the_oldest_lot(self):
        pf = {"cash": 0, "positions": [{"ticker": "INFY", "shares": 3, "lots": [
            {"id": "INFY-1", "date": "2025-01-02", "shares": 2, "cost": 2800.0},
            {"id": "INFY-2", "date": "2026-01-02", "shares": 1, "cost": 1500.0}]}]}
        with open(self.pf, "w") as fh:
            json.dump(pf, fh)
        code, text, _ = run(["fill", "--symbol", "INFY", "--side", "sell", "--qty", "2", "--price", "1490",
                             "--date", TODAY, "--portfolio", self.pf, "--config", self.cfg, "--state", self.state])
        self.assertEqual(code, 0)
        with open(self.pf) as fh:
            pf = json.load(fh)
        self.assertEqual(pf["cash"], 2980.0)
        lots = pf["positions"][0]["lots"]
        self.assertEqual([l["id"] for l in lots], ["INFY-2"])
        self.assertEqual((lots[0]["shares"], lots[0]["cost"]), (1, 1500.0))
        self.assertEqual(self.state_doc()["orders"][-1]["status"], "filled")
        code, _, err = run(["fill", "--symbol", "INFY", "--side", "sell", "--qty", "5", "--price", "1490",
                            "--portfolio", self.pf, "--config", self.cfg, "--state", self.state])
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
