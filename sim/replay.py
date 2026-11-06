"""
Replay of published cases through the trained SafePause score.
Reconstructed from news reports. Where a report gives a total but not the split,
equal splits are assumed. Cautious defaults: details typed (not pasted), no
hesitation, receiving accounts NOT on any risk list, no prior credits.
"""
import json, math, os
HERE = os.path.dirname(__file__)
M = json.load(open(os.path.join(HERE, "results", "model.json")))
F = list(M["std_weights"])

def feats(amt, typ, new, new72, out72, rising, fdb, call, age, bal, pays_per_day=0.4):
    lar = math.log(amt / typ)
    x = dict(log_amt_ratio=lar, new_payee=new, frac_balance=min(amt / bal, 1.5), fd_break_72h=fdb,
             new_payee_pays_72h=new72, outflow_72h=math.log1p(out72 / (typ * (pays_per_day * 3 + 1))),
             rising_new=rising, on_call=call, call_unknown=call, remote_app=0, pasted=0, hesitation=0,
             credit_new_14d=0, payee_flag=0, senior70=int(age >= 70), night=0)
    x["x_new_unknown_call"] = x["new_payee"] * x["call_unknown"]; x["x_fd_new"] = fdb * new
    x["x_amt_new"] = lar * new
    L = [math.log(v) for v in (3, 10, 30, 100)]
    x.update(band_3_10x=int(L[0] <= lar < L[1]), band_10_30x=int(L[1] <= lar < L[2]), band_30_100x=int(L[2] <= lar < L[3]),
             band_100x_plus=int(lar >= L[3]), amt_ge_50k=int(amt >= 50000), amt_ge_2L=int(amt >= 200000),
             x_new_big=int(new and lar >= L[1]))
    return x

def score(x):
    z = sum(M["std_weights"][f] * (x[f] - M["mean"][f]) / M["sd"][f] for f in F) + M["bias"]
    return 1 / (1 + math.exp(-z))

def tier(p):
    return "HOLD" if p >= M["t_high"] else "PAUSE" if p >= M["t_med"] else "pay"

CASES = [
    dict(name="Hyderabad, Oct 2026", src="The420.in", age=80, typ=3000, balance=16000000, fd_broken=0, call=1,
         pays=[(2500000, k % 2) for k in range(6)], note="6 transfers, 23-27 Oct, > Rs 1.5 cr, 2 accounts; equal split assumed"),
    dict(name="Jodhpur, Feb 2026", src="ETV Bharat, 24 Feb 2026", age=75, typ=3000, balance=21000000, fd_broken=1, call=1,
         pays=[(18500000, 0), (2200000, 1)], note="Rs 1.85 cr RTGS, then Rs 22 lakh NEFT attempt after FD closed"),
    dict(name="Navi Mumbai, Nov 2024", src="Free Press Journal, 29 Nov 2024", age=80, typ=3000, balance=3500000, fd_broken=1,
         call=1, pays=[(731000, 0), (731000, 1), (732000, 2), (1200000, 3)],
         note="Rs 21.94 lakh to various accounts (3 equal parts assumed), then Rs 12 lakh stopped by a manager"),
]
out = []
for c in CASES:
    hist = []; bal = c["balance"]; rows = []; acc_seen = set()
    for i, (amt, acc) in enumerate(c["pays"]):
        new = int(acc not in acc_seen)
        prev_new = [h for h in hist if h[2]]
        x = feats(amt, c["typ"], new, sum(h[2] for h in hist), sum(h[0] for h in hist),
                  int(bool(new and prev_new and amt > prev_new[-1][0] * 1.1)), c["fd_broken"], c["call"], c["age"], bal)
        p = score(x); rows.append(dict(n=i + 1, amount=amt, new=new, score=round(p, 4), tier=tier(p)))
        hist.append((amt, acc, new)); acc_seen.add(acc); bal -= amt
    first = next((r for r in rows if r["tier"] != "pay"), None)
    behind = sum(r["amount"] for r in rows if first and r["n"] >= first["n"])
    total = sum(r["amount"] for r in rows)
    out.append(dict(case=c["name"], source=c["src"], note=c["note"], payments=rows,
                    first_paused=first["n"] if first else None, amount_behind_pause=behind, total=total))
    print(c["name"], [f'{r["n"]}:{r["amount"]/1e5:.1f}L {r["tier"]} {r["score"]:.3f}' for r in rows],
          "| first pause at", first and first["n"], f"| {behind/1e5:.1f}L of {total/1e5:.1f}L behind a pause")
json.dump(out, open(os.path.join(HERE, "results", "replay.json"), "w"), indent=1)
