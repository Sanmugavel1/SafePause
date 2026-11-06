"""
SafePause decision pipeline.

  payment request  ->  1 build signals  ->  2 risk score  ->  3 decide tier
                   ->  4 act (pay / silent pause / hold)  ->  5 alert family + open officer case
                   ->  6 outcome (release / stop and return money)  ->  audit log

The risk score is the same logistic model trained in ../../sim/evaluate.py
(weights in model.json). The AI never moves or permanently blocks money: a
pause always ends in release unless a person (family member or bank officer)
says stop.
"""
import json, math, os, sqlite3, threading, time, uuid

HERE = os.path.dirname(__file__)
MODEL = json.load(open(os.path.join(HERE, "model.json")))
F = list(MODEL["std_weights"].keys())
DEMO_SPEED = float(os.environ.get("DEMO_SPEED", "60"))   # 60 = one real second is one demo minute
PAUSE_MIN, HOLD_MIN = 30, 240
DB_PATH = os.environ.get("SAFEPAUSE_DB", os.path.join(HERE, "..", "safepause.db"))
LOCK = threading.RLock()

REASON_TEXT = {
    "log_amt_ratio": "Amount is {x:.0f} times this customer's usual payment",
    "new_payee": "First payment to this account",
    "frac_balance": "Uses {p:.0f}% of the available balance",
    "fd_break_72h": "Fixed deposit closed in the last 72 hours",
    "new_payee_pays_72h": "{n:.0f} payments to new accounts in the last 72 hours",
    "outflow_72h": "Money going out much faster than usual",
    "rising_new": "Each payment to new accounts is bigger than the last",
    "on_call": "Customer is on a phone or video call",
    "call_unknown": "Call is with a number not in contacts",
    "remote_app": "Screen-sharing or remote-access app is open",
    "pasted": "Account details were pasted, not typed",
    "hesitation": "Customer took much longer than usual to confirm",
    "credit_new_14d": "Received a small credit from an unknown source recently",
    "payee_flag": "Receiving account is on a fraud-risk list",
    "senior70": "Customer is 70 or older",
    "night": "Payment made late at night",
    "x_new_unknown_call": "New account while on a call with an unknown number",
    "x_fd_new": "Fixed deposit closed, then a new account paid",
    "x_amt_new": "Large amount to a new account",
    "band_3_10x": "Amount is 3 to 10 times the usual payment",
    "band_10_30x": "Amount is 10 to 30 times the usual payment",
    "band_30_100x": "Amount is 30 to 100 times the usual payment",
    "band_100x_plus": "Amount is over 100 times the usual payment",
    "amt_ge_50k": "Amount is Rs 50,000 or more",
    "amt_ge_2L": "Amount is Rs 2 lakh or more",
    "x_new_big": "Large amount (10x usual or more) to a new account",
}

def now():
    return time.time()

def db():
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    con.row_factory = sqlite3.Row
    return con

CON = None
def conn():
    global CON
    if CON is None:
        CON = db()
    return CON

def log(kind, payment_id, msg, data=None, ms=None):
    with LOCK:
        conn().execute("insert into events(ts,kind,payment_id,msg,data,ms) values(?,?,?,?,?,?)",
                       (now(), kind, payment_id, msg, json.dumps(data or {}), ms))
        conn().commit()

# ---------------------------------------------------------------- 1. signals
def build_signals(cust, req):
    c = conn()
    t = now()
    day = 86400 / DEMO_SPEED                # one demo day, in real seconds
    hist = c.execute("select * from payments where customer_id=? and status in ('paid','paused','held') order by ts",
                     (cust["id"],)).fetchall()
    payee = c.execute("select * from payees where customer_id=? and account=?", (cust["id"], req["account"])).fetchone()
    first_paid = payee["first_paid_ts"] if payee else None
    is_new = 1 if (first_paid is None or t - first_paid < day) else 0
    amt = float(req["amount"])
    typ = cust["typical_amount"]
    h72 = [h for h in hist if t - h["ts"] <= 3 * day]
    newpay72 = sum(1 for h in h72 if h["is_new_payee"])
    out72 = sum(h["amount"] for h in h72)
    base = typ * (cust["pays_per_day"] * 3 + 1)
    prev_new = [h for h in hist if t - h["ts"] <= 7 * day and h["is_new_payee"]]
    rising = 1 if (is_new and prev_new and amt > prev_new[-1]["amount"] * 1.1) else 0
    fd = c.execute("select max(ts) m from fd_events where customer_id=?", (cust["id"],)).fetchone()["m"]
    fdb = 1 if (fd and t - fd <= 3 * day) else 0
    cr = c.execute("select max(ts) m from credits where customer_id=? and from_new=1", (cust["id"],)).fetchone()["m"]
    credit_new = 1 if (cr and t - cr <= 14 * day) else 0
    flagged = c.execute("select 1 from risk_list where account=?", (req["account"],)).fetchone() is not None
    dev = req.get("device", {})
    conf_ms = float(dev.get("confirm_ms", cust["confirm_ms_mean"]))
    hes = (conf_ms - cust["confirm_ms_mean"]) / max(cust["confirm_ms_sd"], 1)
    lar = math.log(max(amt, 1) / typ)
    hour = time.localtime().tm_hour
    on_call = 1 if dev.get("on_call") else 0
    unk = 1 if (on_call and dev.get("caller_unknown")) else 0
    x = dict(log_amt_ratio=lar, new_payee=is_new, frac_balance=min(amt / max(cust["balance"], 1), 1.5),
             fd_break_72h=fdb, new_payee_pays_72h=newpay72, outflow_72h=math.log1p(out72 / base),
             rising_new=rising, on_call=on_call, call_unknown=unk, remote_app=1 if dev.get("remote_app") else 0,
             pasted=1 if dev.get("pasted") else 0, hesitation=max(min(hes, 6), -3), credit_new_14d=credit_new,
             payee_flag=1 if flagged else 0, senior70=1 if cust["age"] >= 70 else 0, night=1 if hour < 7 else 0)
    x["x_new_unknown_call"] = x["new_payee"] * x["call_unknown"]
    x["x_fd_new"] = x["fd_break_72h"] * x["new_payee"]
    x["x_amt_new"] = x["log_amt_ratio"] * x["new_payee"]
    l3, l10, l30, l100 = (math.log(v) for v in (3, 10, 30, 100))
    x["band_3_10x"] = int(l3 <= lar < l10); x["band_10_30x"] = int(l10 <= lar < l30)
    x["band_30_100x"] = int(l30 <= lar < l100); x["band_100x_plus"] = int(lar >= l100)
    x["amt_ge_50k"] = int(amt >= 50000); x["amt_ge_2L"] = int(amt >= 200000)
    x["x_new_big"] = int(is_new and lar >= l10)
    return x

# ---------------------------------------------------------------- 2. score + reasons
def score(x):
    z = sum(MODEL["std_weights"][f] * (x[f] - MODEL["mean"][f]) / MODEL["sd"][f] for f in F) + MODEL["bias"]
    p = 1 / (1 + math.exp(-z))
    contrib = {f: MODEL["std_weights"][f] * (x[f] - MODEL["mean"][f]) / MODEL["sd"][f] for f in F}
    reasons, used = [], set()
    for f, v in sorted(contrib.items(), key=lambda kv: -kv[1]):
        if v <= 0.15 or len(reasons) >= 5:
            continue
        if (f.startswith("band_") or f == "x_new_big" or f == "x_amt_new") and "log_amt_ratio" in used:
            continue
        if f == "log_amt_ratio" and any(u.startswith("band_") for u in used):
            continue
        if f == "x_new_unknown_call" and "call_unknown" in used:
            continue
        used.add(f)
        txt = REASON_TEXT[f].format(x=math.exp(x["log_amt_ratio"]), p=x["frac_balance"] * 100,
                                    n=x["new_payee_pays_72h"])
        reasons.append(dict(code=f, text=txt, weight=round(v, 2)))
    return p, reasons

# ---------------------------------------------------------------- 3. decide
def decide(p, x, cust, amount):
    c = conn()
    open_case = c.execute("select 1 from payments where customer_id=? and status in ('paused','held','stopped') "
                          "and ts > ?", (cust["id"], now() - 86400 / DEMO_SPEED)).fetchone()
    tier = "high" if p >= MODEL["t_high"] else "medium" if p >= MODEL["t_med"] else "low"
    rule = None
    if x["payee_flag"] and amount >= 10000 and tier != "high":
        tier, rule = "high", "Receiving account is on the fraud-risk list"
    stopped = c.execute("select 1 from payments where customer_id=? and status='stopped' and resolved_ts > ?",
                        (cust["id"], now() - 3 * 86400 / DEMO_SPEED)).fetchone()
    if stopped and x["new_payee"] and tier != "high":
        return "high", "A scam payment from this customer was stopped in the last 3 days"
    if open_case and x["new_payee"] and tier == "low":
        tier, rule = "medium", "Customer already has a paused payment today"
    return tier, rule

# ---------------------------------------------------------------- 4-6. act
def submit(customer_id, req):
    t0 = time.perf_counter()
    with LOCK:
        c = conn()
        cust = dict(c.execute("select * from customers where id=?", (customer_id,)).fetchone())
        pid = "PAY-" + uuid.uuid4().hex[:6].upper()
        log("received", pid, f"Payment request: Rs {float(req['amount']):,.0f} to {req['name']} ({req['account']})",
            dict(customer=cust["name"]))
        t1 = time.perf_counter()
        x = build_signals(cust, req)
        t2 = time.perf_counter()
        log("signals", pid, "Signals built from account history and the phone", x, ms=round((t2 - t1) * 1000, 2))
        p, reasons = score(x)
        t3 = time.perf_counter()
        log("score", pid, f"Risk score {p:.3f}", dict(reasons=reasons), ms=round((t3 - t2) * 1000, 2))
        tier, rule = decide(p, x, cust, float(req["amount"]))
        is_new = x["new_payee"]
        amt = float(req["amount"])
        if amt > cust["balance"]:
            log("decision", pid, "Declined: not enough balance")
            return dict(id=pid, status="declined", message="Not enough balance")
        c.execute("update customers set balance=balance-? where id=?", (amt, customer_id))
        status = {"low": "paid", "medium": "paused", "high": "held"}[tier]
        limit = None if tier == "low" else now() + (PAUSE_MIN if tier == "medium" else HOLD_MIN) * 60 / DEMO_SPEED
        c.execute("""insert into payments(id,customer_id,ts,amount,payee_name,account,ifsc,is_new_payee,score,tier,status,
                     reasons,signals,release_at,rule) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (pid, customer_id, now(), amt, req["name"], req["account"], req.get("ifsc", ""), is_new, p, tier,
                   status, json.dumps(reasons), json.dumps(x), limit, rule))
        c.execute("insert or ignore into payees(customer_id,account,name,first_paid_ts) values(?,?,?,?)",
                  (customer_id, req["account"], req["name"], now()))
        c.commit()
        t4 = time.perf_counter()
        label = {"low": "Low risk: pay now", "medium": f"Medium risk: silent pause up to {PAUSE_MIN} min",
                 "high": f"High risk: hold up to {HOLD_MIN // 60} h for a bank officer"}[tier]
        log("decision", pid, label + (f" (rule: {rule})" if rule else ""), dict(tier=tier, score=p),
            ms=round((t4 - t3) * 1000, 2))
        if tier == "low":
            log("paid", pid, f"Sent to {req['name']}")
        else:
            log("hold", pid, f"Rs {amt:,.0f} kept in the bank's hold account; customer sees 'Processing'")
            tc = c.execute("select * from trusted_contacts where customer_id=?", (customer_id,)).fetchone()
            if tc:
                c.execute("insert into alerts(payment_id,contact_id,ts,status) values(?,?,?,'sent')", (pid, tc["id"], now()))
                c.commit()
                log("alert", pid, f"Alert sent to {tc['name']} ({tc['relation']}) by SMS and WhatsApp")
            if tier == "high":
                log("case", pid, "Case opened for the bank officer, with reasons")
            elif not tc:
                log("case", pid, "No trusted contact enrolled: added to the officer queue")
        total = round((time.perf_counter() - t0) * 1000, 1)
        log("timing", pid, f"Decision made in {total} ms", ms=total)
        return dict(id=pid, status=status, tier=tier, score=p, reasons=reasons, ms=total)

def resolve(pid, action, by, note=""):
    """action: release | stop.  by: contact | officer | timer"""
    with LOCK:
        c = conn()
        pay = c.execute("select * from payments where id=?", (pid,)).fetchone()
        if not pay or pay["status"] not in ("paused", "held"):
            return dict(ok=False, error="payment is not on hold")
        if action == "release":
            c.execute("update payments set status='paid', resolved_by=?, resolved_ts=?, note=? where id=?",
                      (by, now(), note, pid))
            log("released", pid, f"Released by {by}. Sent to {pay['payee_name']}" + (f". {note}" if note else ""))
        elif action == "stop":
            c.execute("update payments set status='stopped', resolved_by=?, resolved_ts=?, note=? where id=?",
                      (by, now(), note, pid))
            c.execute("update customers set balance=balance+? where id=?", (pay["amount"], pay["customer_id"]))
            c.execute("insert or ignore into risk_list(account,reason,ts) values(?,?,?)",
                      (pay["account"], f"Stopped scam payment {pid}", now()))
            log("stopped", pid, f"Stopped by {by}. Rs {pay['amount']:,.0f} returned to the customer's account" +
                (f". {note}" if note else ""))
            log("report", pid, "Receiving account added to the bank's risk list; report ready for NCRP / 1930")
        c.commit()
        return dict(ok=True)

def contact_reply(alert_id, answer):
    with LOCK:
        c = conn()
        a = c.execute("select * from alerts where id=?", (alert_id,)).fetchone()
        if not a:
            return dict(ok=False)
        c.execute("update alerts set status=?, reply_ts=? where id=?", (answer, now(), alert_id))
        c.commit()
        pay = c.execute("select * from payments where id=?", (a["payment_id"],)).fetchone()
        tc = c.execute("select * from trusted_contacts where id=?", (a["contact_id"],)).fetchone()
        if answer == "expected":
            log("contact", pay["id"], f"{tc['name']}: 'Yes, I know about this payment'")
            if pay["tier"] == "medium":
                return resolve(pay["id"], "release", "family member")
            log("contact", pay["id"], "High-risk hold stays: the officer still decides, with this answer on file")
        elif answer == "not_expected":
            log("contact", pay["id"], f"{tc['name']}: 'No, I don't know about this. Stop it'")
            if pay["tier"] == "medium":
                c.execute("update payments set tier='high', status='held', release_at=? where id=?",
                          (now() + HOLD_MIN * 60 / DEMO_SPEED, pay["id"]))
                c.commit()
                log("case", pay["id"], "Moved to high risk; case opened for the bank officer")
        elif answer == "call_me":
            log("contact", pay["id"], f"{tc['name']} asked the bank to call them")
        return dict(ok=True)

def timer_loop():
    while True:
        time.sleep(1)
        try:
            with LOCK:
                due = conn().execute("select id,tier from payments where status in ('paused','held') and release_at<?",
                                     (now(),)).fetchall()
            for d in due:
                resolve(d["id"], "release", "timer",
                        "Nobody objected within the pause window" if d["tier"] == "medium"
                        else "Hold time ended without an officer decision; released and flagged for follow-up")
        except Exception as e:      # keep the loop alive in a demo
            print("timer error", e)
