"""
SafePause prototype server. Python 3 standard library only (no installs).

    python3 server.py            -> http://localhost:8600
    DEMO_SPEED=60 (default): 1 real second = 1 demo minute, so a 30-minute
    pause lasts 30 s and a 4-hour hold lasts 4 min in the video.

Screens:
    /                 demo stage (all four screens side by side, for the video)
    /app.html         customer's bank app (phone)
    /contact.html     trusted family member's phone
    /officer.html     bank officer console
    /pipeline.html    live pipeline log
    /dashboard.html   bank manager's dashboard
API:
    POST /api/pay            {customer_id, name, account, ifsc, amount, device:{...}}
    GET  /api/state          everything the screens need
    POST /api/officer        {payment_id, action: release|stop, note}
    POST /api/contact        {alert_id, answer: expected|not_expected|call_me}
    POST /api/reset          reseed the demo data
    POST /api/score          {customer_id, ...} -> score only, nothing stored (for integration tests)
"""
import json, os, sys, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from engine import pipeline as P

SCHEMA = """
drop table if exists customers; drop table if exists payees; drop table if exists payments;
drop table if exists trusted_contacts; drop table if exists alerts; drop table if exists events;
drop table if exists fd_events; drop table if exists credits; drop table if exists risk_list;
create table customers(id integer primary key, name text, age int, city text, balance real, fd_balance real,
  typical_amount real, pays_per_day real, confirm_ms_mean real, confirm_ms_sd real, language text);
create table payees(customer_id int, account text, name text, first_paid_ts real, primary key(customer_id, account));
create table payments(id text primary key, customer_id int, ts real, amount real, payee_name text, account text,
  ifsc text, is_new_payee int, score real, tier text, status text, reasons text, signals text, release_at real,
  rule text, resolved_by text, resolved_ts real, note text);
create table trusted_contacts(id integer primary key, customer_id int, name text, relation text, phone text);
create table alerts(id integer primary key, payment_id text, contact_id int, ts real, status text, reply_ts real);
create table events(id integer primary key, ts real, kind text, payment_id text, msg text, data text, ms real);
create table fd_events(customer_id int, ts real, amount real);
create table credits(customer_id int, ts real, amount real, from_new int);
create table risk_list(account text primary key, reason text, ts real);
drop table if exists payee_intel;
create table payee_intel(account text primary key, opened_days int, credits_48h int, states int, note text);
"""

def seed():
    c = P.conn()
    c.executescript(SCHEMA)
    day = 86400 / P.DEMO_SPEED
    t = time.time()
    # Fictional demo customers (no real people).
    c.execute("insert into customers values(1,'Kamala Ramanathan',74,'Chennai',1835000,0,2000,0.4,9000,4000,'Tamil')")
    c.execute("insert into customers values(2,'Rahul Srinivasan',29,'Coimbatore',265000,0,2500,1.2,6000,2500,'English')")
    c.execute("insert into trusted_contacts values(1,1,'Arun Ramanathan','Son','+91 9XXXX XXX21')")
    # Kamala: fixed deposit of Rs 18 lakh closed yesterday (money now in savings), as in published digital-arrest cases
    c.execute("insert into fd_events values(1,?,1800000)", (t - 0.8 * day,))
    known = {1: [("Apollo Pharmacy Adyar", "50200011112222"), ("TNPDCL Electricity", "TNEB0042113"),
                 ("Lakshmi Milk Service", "33010455667"), ("Arun Ramanathan", "60110022334455")],
             2: [("Ravi House Owner", "91002003004"), ("Fresh Mart", "77880011223"), ("Mom", "40500600700")]}
    for cid, lst in known.items():
        for name, acc in lst:
            c.execute("insert into payees values(?,?,?,?)", (cid, acc, name, t - 200 * day))
    # a few past payments so the history is not empty
    import random
    random.seed(4)
    for cid, lst in known.items():
        for k in range(12):
            name, acc = random.choice(lst)
            ts = t - (5 + k * 2) * day
            amt = round(random.uniform(800, 3500), -1)
            c.execute("insert into payments(id,customer_id,ts,amount,payee_name,account,is_new_payee,score,tier,status,"
                      "reasons,signals) values(?,?,?,?,?,?,0,0.01,'low','paid','[]','{}')",
                      (f"OLD-{cid}-{k}", cid, ts, amt, name, acc))
    # Accounts already on a fraud-risk list (stands in for DoT FRI / MuleHunter-style feeds; demo data)
    c.execute("insert into risk_list values('39200178451226','Reported on NCRP twice in 7 days (demo)',?)", (t,))
    # What a receiving-account check could show (demo data; in practice from the receiving bank or a shared mule feed)
    for row in [("91827364550011", 11, 41, 9, "Most credits withdrawn within 30 minutes"),
                ("77120098345566", 6, 58, 12, "Most credits withdrawn within 30 minutes"),
                ("601100224411", 8, 126, 14, "Many small credits, then large transfers out"),
                ("5550001112", 2900, 3, 1, "Business current account, 8 years old")]:
        c.execute("insert into payee_intel values(?,?,?,?,?)", row)
    c.commit()
    P.log("system", None, "Demo data loaded: 2 customers, 1 trusted contact, 1 account on the risk list")

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(HERE, "web"), **k)

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, default=float).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path.startswith("/api/state"):
            return self._json(state())
        return super().do_GET()

    def do_POST(self):
        try:
            b = self._body()
            if self.path == "/api/pay":
                return self._json(P.submit(int(b["customer_id"]), b))
            if self.path == "/api/officer":
                return self._json(P.resolve(b["payment_id"], b["action"], "bank officer", b.get("note", "")))
            if self.path == "/api/contact":
                return self._json(P.contact_reply(int(b["alert_id"]), b["answer"]))
            if self.path == "/api/reset":
                with P.LOCK:
                    seed()
                return self._json(dict(ok=True))
            if self.path == "/api/score":
                with P.LOCK:
                    cust = dict(P.conn().execute("select * from customers where id=?", (int(b["customer_id"]),)).fetchone())
                    x = P.build_signals(cust, b)
                    p, reasons = P.score(x)
                    tier, rule = P.decide(p, x, cust, float(b["amount"]))
                return self._json(dict(score=p, tier=tier, rule=rule, reasons=reasons, signals=x))
            if self.path == "/api/call":
                P.log("officer", b["payment_id"], "Officer called the customer on the registered number (recorded line)")
                return self._json(dict(ok=True))
            if self.path == "/api/credit":
                with P.LOCK:
                    P.conn().execute("insert into credits values(?,?,?,1)", (int(b["customer_id"]), time.time(), float(b["amount"])))
                    P.conn().commit()
                P.log("system", None, f"Incoming credit Rs {float(b['amount']):,.0f} from an unknown account ({b.get('label', 'demo')})")
                return self._json(dict(ok=True))
            if self.path == "/api/fd_break":
                with P.LOCK:
                    P.conn().execute("insert into fd_events values(?,?,?)", (int(b["customer_id"]), time.time(), 0))
                    P.conn().commit()
                P.log("system", None, "Fixed deposit closed (demo control)")
                return self._json(dict(ok=True))
            self._json(dict(error="not found"), 404)
        except Exception as e:
            self._json(dict(error=str(e)), 500)

def state():
    with P.LOCK:
        c = P.conn()
        q = lambda s, a=(): [dict(r) for r in c.execute(s, a).fetchall()]
        now = time.time()
        pays = q("select * from payments where id not like 'OLD-%' order by ts desc limit 50")
        for p in pays:
            p["reasons"] = json.loads(p["reasons"] or "[]"); p["signals"] = json.loads(p["signals"] or "{}")
            p["seconds_left"] = max(0, (p["release_at"] or 0) - now) if p["status"] in ("paused", "held") else 0
            p["demo_minutes_left"] = round(p["seconds_left"] * P.DEMO_SPEED / 60)
        return dict(
            now=now, demo_speed=P.DEMO_SPEED, t_med=P.MODEL["t_med"], t_high=P.MODEL["t_high"],
            customers=q("select * from customers"),
            payees=q("select * from payees"),
            contacts=q("select * from trusted_contacts"),
            alerts=q("select a.*, p.amount, p.payee_name, p.account, p.tier, p.status pay_status, p.customer_id "
                     "from alerts a join payments p on p.id=a.payment_id order by a.ts desc"),
            payments=pays,
            history=q("select * from payments where id like 'OLD-%' order by ts desc"),
            events=q("select * from events order by id desc limit 120"),
            risk_list=q("select * from risk_list"),
            intel=q("select * from payee_intel"),
            fd=q("select * from fd_events order by ts desc"))

if __name__ == "__main__":
    seed()
    threading.Thread(target=P.timer_loop, daemon=True).start()
    port = int(os.environ.get("PORT", "8600"))
    print(f"SafePause prototype on http://localhost:{port}  (DEMO_SPEED={P.DEMO_SPEED})")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
