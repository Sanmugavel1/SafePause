"""
SafePause simulation, step 1: synthetic bank customers and payments.

Everything here is SYNTHETIC. Scam patterns are modelled on published Indian
cases (see ../research/RESEARCH_NOTES.md) and the amount mix is calibrated to
the RBI discussion paper of 9 Apr 2026 (fraud payments >= Rs 10,000 are about
45% by count and 98.5% by value).

Output: data/payments.npz (one row per payment, with the signals a bank app
can see at the moment of payment) and data/meta.json.
"""
import json, math, os
import numpy as np

SEED = 7
N_CUST = 30000
DAYS = 60
SPLIT_DAY = 30                       # days 0-29 train, 30-59 test
N_EPISODES = 6000                    # scam episodes (oversampled; metrics are per episode)
TRAIN_TYPES = ["digital_arrest", "investment", "kyc_call", "small_ticket"]
HELDOUT_TYPES = ["task_job", "relative_voice"]   # never seen in training
TYPE_SHARE = {"digital_arrest": .08, "investment": .10, "kyc_call": .06,
              "small_ticket": .66, "task_job": .05, "relative_voice": .05}

rng = np.random.default_rng(SEED)
OUT = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT, exist_ok=True)

# ---------------- customers ----------------
age_band = rng.choice(4, N_CUST, p=[.35, .40, .15, .10])   # 0:18-35 1:36-59 2:60-69 3:70+
senior70 = age_band == 3
typ_amt = np.exp(rng.normal(math.log(1500), .8, N_CUST))
savings0 = np.exp(rng.normal(math.log(80000), 1.0, N_CUST)) * np.where(age_band >= 2, 2.0, 1.0)
has_fd = rng.random(N_CUST) < np.array([.15, .35, .60, .70])[age_band]
fd0 = np.where(has_fd, np.exp(rng.normal(math.log(500000), 1.0, N_CUST)) * np.where(age_band >= 2, 2, 1), 0)
rate = np.exp(rng.normal(math.log(.25), .6, N_CUST))      # genuine push payments per day

rows = []   # each: dict of raw event fields (features computed later in time order)

def add(c, t, amt, new, call, unk, paste, hes, remote=0, scam=0, stype="", ep=-1,
        fd_break_before=None, credit_new_before=None, flag=0, kind="normal"):
    rows.append(dict(c=c, t=t, amt=float(max(amt, 50.0)), new=int(new), call=int(call),
                     unk=int(unk and call), paste=int(paste), hes=float(hes), remote=int(remote),
                     scam=int(scam), stype=stype, ep=ep, fdb=fd_break_before,
                     cnew=credit_new_before, flag=int(flag), kind=kind))

fd_breaks = {}      # cust -> list of times (minutes) when an FD was broken
credits_new = {}    # cust -> list of times a small credit arrived from a new counterparty

MIN_DAY = 1440
T_END = DAYS * MIN_DAY

def daytime(t_day):
    """random time on a given day, mostly 8am-10pm"""
    if rng.random() < .05:
        return t_day * MIN_DAY + rng.uniform(0, 7 * 60)
    return t_day * MIN_DAY + rng.uniform(8 * 60, 22 * 60)

# ---------------- genuine behaviour ----------------
for c in range(N_CUST):
    n = rng.poisson(rate[c] * DAYS)
    days = rng.integers(0, DAYS, n)
    for d in days:
        t = daytime(d)
        new = rng.random() < .20
        amt = typ_amt[c] * np.exp(rng.normal(0, .9)) * (.6 if new else 1)
        call = rng.random() < .15
        add(c, t, amt, new, call, rng.random() < .35, rng.random() < (.35 if new else .02),
            rng.normal(0, 1), remote=rng.random() < .003, flag=rng.random() < .002)
    # hard negatives: unusual but genuine payments
    for _ in range(rng.poisson(.35)):          # big one-off to a new payee (vehicle, fees, hospital, deposit)
        t = daytime(rng.integers(0, DAYS))
        add(c, t, typ_amt[c] * rng.uniform(10, 60), 1, rng.random() < .3, rng.random() < .4,
            rng.random() < .6, rng.normal(.5, 1), kind="big_new")
    if has_fd[c] and rng.random() < (.06 if age_band[c] >= 2 else .03):   # FD broken for a real need
        d = rng.integers(0, DAYS); tb = daytime(d)
        fd_breaks.setdefault(c, []).append(tb)
        for k in range(rng.integers(1, 4)):
            t = tb + rng.uniform(30, 72 * 60)
            add(c, t, fd0[c] * rng.uniform(.1, .5), rng.random() < .6, rng.random() < .4,
                rng.random() < .5, rng.random() < .5, rng.normal(.7, 1), kind="fd_need")
    if rng.random() < .04:          # family emergency, paid while on the phone
        t = daytime(rng.integers(0, DAYS))
        add(c, t, typ_amt[c] * rng.uniform(5, 30), rng.random() < .4, 1, rng.random() < .15,
            rng.random() < .3, rng.normal(.8, 1), kind="family_emergency")
    if rng.random() < .03:         # contractor / builder instalments, rising
        d0 = rng.integers(0, DAYS - 12); a = typ_amt[c] * rng.uniform(5, 15)
        for k in range(rng.integers(3, 6)):
            add(c, daytime(d0 + 2 * k), a * (1 + .4 * k), k == 0, rng.random() < .2, 0,
                rng.random() < .3, rng.normal(0, 1), kind="instalments")
    for _ in range(rng.poisson(.25)):          # genuine refund/cashback from a new counterparty
        credits_new.setdefault(c, []).append(daytime(rng.integers(0, DAYS)))

n_genuine = len(rows)

# ---------------- scam episodes ----------------
def pick_victim(stype):
    w = {"digital_arrest": [.05, .20, .35, .40], "investment": [.35, .50, .12, .03],
         "kyc_call": [.25, .35, .20, .20], "small_ticket": [.45, .40, .10, .05],
         "task_job": [.70, .27, .03, 0], "relative_voice": [.05, .20, .30, .45]}[stype]
    band = rng.choice(4, p=w)
    return int(rng.choice(np.flatnonzero(age_band == band)))

types = list(TYPE_SHARE)
ep_types = rng.choice(types, N_EPISODES, p=[TYPE_SHARE[k] for k in types])
episodes = []
for ep, stype in enumerate(ep_types):
    c = pick_victim(stype)
    liquid = savings0[c] + fd0[c]
    d0 = int(rng.integers(0, DAYS - 10))
    t0 = daytime(d0)
    flag_p = .25                                   # share of mule payees already on a risk list
    pays = []
    if stype == "digital_arrest":
        if has_fd[c] and rng.random() < .7:
            fd_breaks.setdefault(c, []).append(t0 + rng.uniform(60, 600))
        n = rng.integers(2, 9); total = max(liquid * rng.uniform(.5, .95), 300000)
        w = np.sort(rng.uniform(.5, 2, n)); w = w / w.sum()
        t = t0 + 720
        for k in range(n):
            t += rng.uniform(4, 40) * 60
            pays.append((t, total * w[k], rng.random() < .8, rng.random() < .85, 1, rng.random() < .8,
                         rng.normal(1.2, 1), rng.random() < .1))
    elif stype == "investment":
        n = rng.integers(4, 16); a = rng.uniform(5000, 20000)
        credits_new.setdefault(c, []).append(t0 + rng.uniform(1, 3) * MIN_DAY)
        t = t0
        for k in range(n):
            t += rng.uniform(.5, 4) * MIN_DAY
            if t > T_END: break
            pays.append((t, min(a, max(liquid * .6, 200000)), rng.random() < .6, rng.random() < .15, rng.random() < .6,
                         rng.random() < .7, rng.normal(.3, 1), 0))
            a *= rng.uniform(1.3, 2.6)
    elif stype == "kyc_call":
        for k in range(rng.integers(1, 3)):
            pays.append((t0 + k * rng.uniform(5, 30), rng.uniform(10000, 100000), 1, rng.random() < .9,
                         rng.random() < .9, rng.random() < .6, rng.normal(.8, 1), rng.random() < .3))
    elif stype == "small_ticket":                  # marketplace / fake QR / small advance
        for k in range(rng.integers(1, 5)):
            pays.append((t0 + k * rng.uniform(5, 120), np.exp(rng.normal(math.log(2500), .7)),
                         1, rng.random() < .4, rng.random() < .6, rng.random() < .5, rng.normal(.2, 1), 0))
    elif stype == "task_job":                      # held out: like/review tasks, rising "deposits"
        credits_new.setdefault(c, []).append(t0)
        a = rng.uniform(1000, 5000); t = t0 + 120
        for k in range(rng.integers(3, 9)):
            t += rng.uniform(.3, 8) * 60
            pays.append((t, a, rng.random() < .5, rng.random() < .05, 0, rng.random() < .9,
                         rng.normal(.4, 1), 0))
            a *= rng.uniform(1.4, 2.5)
    elif stype == "relative_voice":                # held out: fake relative in trouble (cloned voice)
        pays.append((t0, rng.uniform(25000, 300000), 1, 1, rng.random() < .7, rng.random() < .4,
                     rng.normal(-.3, 1), 0))
    for k, (t, amt, new, call, unk, paste, hes, remote) in enumerate(pays):
        add(c, t, amt, new, call, unk, paste, hes, remote=remote, scam=1, stype=stype, ep=ep,
            flag=rng.random() < flag_p)
    episodes.append(dict(ep=ep, c=c, stype=stype, n=len(pays), start=t0))

# ---------------- features, computed in time order per customer ----------------
rows.sort(key=lambda r: (r["c"], r["t"]))
F = ["log_amt_ratio", "new_payee", "frac_balance", "fd_break_72h", "new_payee_pays_72h",
     "outflow_72h", "rising_new", "on_call", "call_unknown", "remote_app", "pasted",
     "hesitation", "credit_new_14d", "payee_flag", "senior70", "night",
     "x_new_unknown_call", "x_fd_new", "x_amt_new"]
X = np.zeros((len(rows), len(F)), dtype=np.float32)
meta = {k: [] for k in ["c", "t", "amt", "scam", "stype", "ep", "kind", "senior70", "new"]}
prev_c = -1
for i, r in enumerate(rows):
    c = r["c"]
    if c != prev_c:
        hist = []                 # (t, amt, new)
        bal = savings0[c]
        prev_c = c
    t, amt = r["t"], r["amt"]
    fdb = any(0 <= t - x <= 72 * 60 for x in fd_breaks.get(c, []))
    if fdb and bal < amt:         # broken FD lands in savings
        bal += fd0[c]
    h72 = [h for h in hist if t - h[0] <= 72 * 60]
    h7d = [h for h in hist if t - h[0] <= 7 * MIN_DAY and h[2]]
    out72 = sum(h[1] for h in h72)
    base = typ_amt[c] * (rate[c] * 3 + 1)
    rising = bool(h7d) and r["new"] and amt > h7d[-1][1] * 1.1
    cn = any(0 <= t - x <= 14 * MIN_DAY for x in credits_new.get(c, []))
    lar = math.log(amt / typ_amt[c])
    night = (t % MIN_DAY) < 7 * 60
    X[i] = [lar, r["new"], min(amt / max(bal, 1), 1.5), fdb, sum(h[2] for h in h72),
            math.log1p(out72 / base), rising, r["call"], r["unk"], r["remote"], r["paste"],
            r["hes"], cn, r["flag"], senior70[c], night,
            r["new"] * r["unk"], fdb * r["new"], lar * r["new"]]
    hist.append((t, amt, r["new"]))
    bal = max(bal - amt, 0) + typ_amt[c] * rate[c] * .2   # crude income top-up
    for k in meta:
        if k == "senior70": meta[k].append(bool(senior70[c]))
        elif k == "new": meta[k].append(r["new"])
        else: meta[k].append(r[k])

np.savez_compressed(os.path.join(OUT, "payments.npz"), X=X,
                    **{k: np.array(v) for k, v in meta.items()})

# ---------------- calibration check vs RBI ----------------
amt = np.array(meta["amt"]); sc = np.array(meta["scam"]) == 1
a = amt[sc]
cal = dict(share_count_ge10k=float((a >= 10000).mean()), share_value_ge10k=float(a[a >= 10000].sum() / a.sum()),
           share_value_ge50k=float(a[a >= 50000].sum() / a.sum()),
           rbi_target=dict(share_count_ge10k=.45, share_value_ge10k=.985, share_value_ge50k=.92))
info = dict(n_customers=N_CUST, days=DAYS, n_payments=len(rows), n_genuine=int((~sc).sum()),
            n_scam_payments=int(sc.sum()), n_episodes=N_EPISODES, features=F,
            train_types=TRAIN_TYPES, heldout_types=HELDOUT_TYPES, split_day=SPLIT_DAY,
            calibration=cal, episodes=episodes,
            genuine_kinds={k: int((np.array(meta["kind"])[~sc] == k).sum())
                           for k in ["normal", "big_new", "fd_need", "family_emergency", "instalments"]})
json.dump(info, open(os.path.join(OUT, "meta.json"), "w"), indent=1, default=float)
print(json.dumps({k: v for k, v in info.items() if k != "episodes"}, indent=1, default=float))
