"""
SafePause simulation, step 2: train the risk score, then compare five policies
over many Monte Carlo runs of uncertain human behaviour.

Policies (all applied to the SAME synthetic payments, test month only):
  P0 No safeguard            - instant payments, as today
  P1 Rules + warning         - new payee & >= Rs 50k, or >= 5x usual: "are you sure?" pop-up
  P2 Blanket 1-hour lag      - RBI DP option 1: every push payment >= Rs 10k waits 60 min
  P3 Trusted person (70+)    - RBI DP option 2: 70+ customers, every payment > Rs 50k
  P4 SafePause               - risk score; medium = silent 30-min pause + trusted-contact
                               alert; high = hold up to 4 h + bank officer review

Training uses days 0-29 and only TRAIN_TYPES. Testing uses days 30-59 and all
scam types, including two types the model never saw (task_job, relative_voice).
"""
import json, math, os
import numpy as np

HERE = os.path.dirname(__file__)
D = np.load(os.path.join(HERE, "data", "payments.npz"))
META = json.load(open(os.path.join(HERE, "data", "meta.json")))
OUT = os.path.join(HERE, "results"); os.makedirs(OUT, exist_ok=True)
F = META["features"]
X, amt, scam, stype, ep = D["X"], D["amt"], D["scam"] == 1, D["stype"], D["ep"]
t, cust, senior, new = D["t"], D["c"], D["senior70"], D["new"] == 1
day = t / 1440

# scorecard-style amount bands (banks' usual way to keep a linear score explainable)
def derive(X, amt):
    lar = X[:, F.index("log_amt_ratio")]; nw = X[:, F.index("new_payee")]
    extra = np.stack([(lar >= np.log(3)) & (lar < np.log(10)), (lar >= np.log(10)) & (lar < np.log(30)),
                      (lar >= np.log(30)) & (lar < np.log(100)), lar >= np.log(100),
                      amt >= 50000, amt >= 200000, (nw == 1) & (lar >= np.log(10))], 1).astype(np.float32)
    return np.concatenate([X, extra], 1)
EXTRA = ["band_3_10x", "band_10_30x", "band_30_100x", "band_100x_plus", "amt_ge_50k", "amt_ge_2L", "x_new_big"]
X = derive(X, amt); F = F + EXTRA
train = (day < META["split_day"]) & (~scam | np.isin(stype, META["train_types"]))
test = day >= META["split_day"]
TEST_CUST_MONTHS = META["n_customers"] * 1.0          # 30 test days = 1 month per customer

# ---------------- 1. logistic regression (numpy, L2, class-weighted) ----------------
mu, sd = X[train].mean(0), X[train].std(0) + 1e-6
Z = (X - mu) / sd
y = scam.astype(float)
w_pos = (~scam[train]).sum() / scam[train].sum()
sw = np.where(y[train] == 1, w_pos, 1.0); sw /= sw.mean()
Ztr, ytr = Z[train], y[train]
w = np.zeros(Z.shape[1]); b = 0.0
for it in range(3000):
    p = 1 / (1 + np.exp(-(Ztr @ w + b)))
    g = (p - ytr) * sw
    w -= .1 * (Ztr.T @ g / len(ytr) + 1e-3 * w)
    b -= .1 * g.mean()
score = 1 / (1 + np.exp(-(Z @ w + b)))

# ---------------- 2. tier thresholds, chosen on TRAINING genuine payments ----------------
g_tr = train & ~scam
MED_RATE, HIGH_RATE = .004, .0006      # at most 0.4% of genuine payments paused, 0.06% held
t_med = float(np.quantile(score[g_tr], 1 - MED_RATE))
t_high = float(np.quantile(score[g_tr], 1 - HIGH_RATE))
tier = np.where(score >= t_high, 2, np.where(score >= t_med, 1, 0))

def auc(s, lab):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    npos = lab.sum(); return float((r[lab].sum() - npos * (npos + 1) / 2) / (npos * (len(s) - npos)))
m_seen = test & (~scam | np.isin(stype, META["train_types"]))
m_un = test & (~scam | np.isin(stype, META["heldout_types"]))
model_info = dict(weights={f: float(v / s) for f, v, s in zip(F, w, sd)},
                  std_weights={f: float(v) for f, v in zip(F, w)},
                  mean=dict(zip(F, map(float, mu))), sd=dict(zip(F, map(float, sd))), bias=float(b),
                  t_med=t_med, t_high=t_high,
                  auc_test_seen_types=auc(score[m_seen], scam[m_seen]),
                  auc_test_unseen_types=auc(score[m_un], scam[m_un]))
json.dump(model_info, open(os.path.join(OUT, "model.json"), "w"), indent=1)

# ---------------- 3. uncertain behaviour (sampled every Monte Carlo run) ----------------
TYPES = ["digital_arrest", "investment", "kyc_call", "small_ticket", "task_job", "relative_voice"]
def draw(r):
    u = lambda a, b: r.uniform(a, b)
    return dict(
        warn_ignored={"digital_arrest": u(.9, .98), "investment": u(.85, .97), "kyc_call": u(.75, .92),
                      "small_ticket": u(.75, .92), "task_job": u(.85, .97), "relative_voice": u(.75, .92)},
        self_cancel_1h={"digital_arrest": u(.02, .08), "investment": u(.01, .05), "kyc_call": u(.08, .2),
                        "small_ticket": u(.05, .15), "task_job": u(.03, .1), "relative_voice": u(.1, .3)},
        scam_whitelisted=u(.2, .5),            # scammer tells victim to whitelist the payee (RBI's own concern)
        genuine_whitelisted=u(.4, .7),
        tc_enrol_senior=u(.4, .7), tc_enrol_other=u(.2, .45),
        tc_reply_30min=u(.55, .8),
        tc_spots={"digital_arrest": u(.75, .95), "investment": u(.4, .7), "kyc_call": u(.6, .9),
                  "small_ticket": u(.3, .6), "task_job": u(.5, .8), "relative_voice": u(.7, .95)},
        officer_spots_high=u(.45, .7), officer_spots_med=u(.1, .25), officer_spots_flagged=u(.8, .95),
        moves_bank_if_told=u(.3, .6),       # scammer reacts when the app openly says "held"
    )

def run(theta, r, variant="full"):
    """returns dict policy -> metrics for one Monte Carlo draw"""
    res = {}
    te_s = np.flatnonzero(test & scam)
    order = te_s[np.lexsort((t[te_s], ep[te_s]))]
    enrolled_c = {}
    def enrolled(c):
        if c not in enrolled_c:
            p = theta["tc_enrol_senior"] if CUST_SENIOR[c] else theta["tc_enrol_other"]
            enrolled_c[c] = r.random() < p
        return enrolled_c[c]
    for pol in ["P0", "P1", "P2", "P3", "P4"] + (["P4_no_tc", "P4_open_hold"] if variant == "full" else []):
        lost = saved = 0.0; stopped_eps = set(); ep_any_loss = {}
        by_type = {k: [0.0, 0.0] for k in TYPES}
        for i in order:
            e, st, a = int(ep[i]), str(stype[i]), float(amt[i])
            if e in stopped_eps:
                saved += a; by_type[st][1] += a; continue
            p_stop = 0.0
            if pol == "P1":
                if (new[i] and a >= 50000) or X[i, 0] >= math.log(5):
                    p_stop = 1 - theta["warn_ignored"][st]
            elif pol == "P2":
                if a >= 10000 and r.random() > theta["scam_whitelisted"]:
                    p_stop = theta["self_cancel_1h"][st]
            elif pol == "P3":
                if senior[i] and a > 50000:
                    p_stop = theta["tc_reply_30min"] * theta["tc_spots"][st]   # waits for reply
            elif pol.startswith("P4"):
                k = tier[i]
                tc = 0.0 if pol == "P4_no_tc" else (enrolled(int(cust[i])) * theta["tc_reply_30min"] * theta["tc_spots"][st])
                if k == 1:
                    p_stop = 1 - (1 - tc) * (1 - theta["officer_spots_med"])
                elif k == 2:
                    off = theta["officer_spots_flagged"] if X[i, F.index("payee_flag")] else theta["officer_spots_high"]
                    p_stop = 1 - (1 - tc) * (1 - off)
                if pol == "P4_open_hold" and k > 0 and r.random() < theta["moves_bank_if_told"]:
                    p_stop = 0.0                      # victim told -> scammer moves them to another bank
            if r.random() < p_stop:
                stopped_eps.add(e); saved += a; by_type[st][1] += a
            else:
                lost += a; by_type[st][0] += a; ep_any_loss[e] = True
        eps = set(int(x) for x in ep[order])
        res[pol] = dict(value_stopped=saved / (saved + lost), victims_fully_protected=1 - len(ep_any_loss) / len(eps),
                        by_type={k: (v[1] / (v[0] + v[1]) if v[0] + v[1] else None) for k, v in by_type.items()})
    # ---- genuine side (test month) ----
    g = np.flatnonzero(test & ~scam); ag = amt[g]
    n_g = len(g)
    res["P0"].update(delayed_share=0.0, delayed_per_1000_cust_month=0.0, median_delay_min=0.0, popups_per_1000=0.0)
    p1 = ((new[g] & (ag >= 50000)) | (X[g, 0] >= math.log(5)))
    res["P1"].update(delayed_share=0.0, delayed_per_1000_cust_month=0.0, median_delay_min=0.0,
                     popups_per_1000=float(p1.sum() / TEST_CUST_MONTHS * 1000))
    p2 = (ag >= 10000) & (r.random(n_g) > theta["genuine_whitelisted"] * (~new[g]))
    res["P2"].update(delayed_share=float(p2.mean()), delayed_per_1000_cust_month=float(p2.sum() / TEST_CUST_MONTHS * 1000),
                     median_delay_min=60.0, popups_per_1000=0.0)
    p3 = senior[g] & (ag > 50000)
    d3 = np.minimum(r.lognormal(math.log(20), .9, p3.sum()), 240)
    res["P3"].update(delayed_share=float(p3.mean()), delayed_per_1000_cust_month=float(p3.sum() / TEST_CUST_MONTHS * 1000),
                     median_delay_min=float(np.median(d3)) if len(d3) else 0.0, popups_per_1000=0.0)
    k = tier[g]
    d_med = np.minimum(r.lognormal(math.log(12), .8, (k == 1).sum()), 30)
    d_high = np.minimum(r.lognormal(math.log(35), .7, (k == 2).sum()), 240)
    dl = np.concatenate([d_med, d_high])
    for pol in [p for p in res if p.startswith("P4")]:
        res[pol].update(delayed_share=float((k > 0).mean()),
                        delayed_per_1000_cust_month=float((k > 0).sum() / TEST_CUST_MONTHS * 1000),
                        median_delay_min=float(np.median(dl)) if len(dl) else 0.0, popups_per_1000=0.0,
                        officer_cases_per_lakh_cust_day=float((k == 2).sum() / TEST_CUST_MONTHS / 30 * 1e5))
    return res

CUST_SENIOR = np.zeros(META["n_customers"], bool); CUST_SENIOR[cust] = senior

N_RUNS = 200
r = np.random.default_rng(11)
runs, thetas = [], []
for k in range(N_RUNS):
    th = draw(r); thetas.append(th); runs.append(run(th, r))

def summ(vals):
    v = np.array([x for x in vals if x is not None])
    return dict(median=float(np.median(v)), p05=float(np.quantile(v, .05)), p95=float(np.quantile(v, .95)))
pols = list(runs[0])
summary = {}
for p in pols:
    summary[p] = {m: summ([rr[p][m] for rr in runs]) for m in
                  ["value_stopped", "victims_fully_protected", "delayed_share", "delayed_per_1000_cust_month",
                   "median_delay_min", "popups_per_1000"]}
    summary[p]["by_type"] = {ty: summ([rr[p]["by_type"][ty] for rr in runs]) for ty in TYPES}
    if "officer_cases_per_lakh_cust_day" in runs[0][p]:
        summary[p]["officer_cases_per_lakh_cust_day"] = summ([rr[p]["officer_cases_per_lakh_cust_day"] for rr in runs])

# ---------------- 4. threshold sweep for the main chart (median behaviour) ----------------
mid = draw(np.random.default_rng(0))
for key in mid:
    if isinstance(mid[key], dict):
        mid[key] = {k: float(np.mean([th[key][k] for th in thetas])) for k in mid[key]}
    else:
        mid[key] = float(np.mean([th[key] for th in thetas]))
sweep = []
base_tier = tier.copy()
for rate_m in [.0005, .001, .002, .003, .004, .006, .008, .012, .02, .03]:
    tm = float(np.quantile(score[g_tr], 1 - rate_m)); th_ = float(np.quantile(score[g_tr], 1 - min(HIGH_RATE * rate_m / MED_RATE, rate_m)))
    tier[:] = np.where(score >= th_, 2, np.where(score >= tm, 1, 0))
    vals = [run(mid, np.random.default_rng(100 + j), variant="lite")["P4"] for j in range(15)]
    sweep.append(dict(paused_rate_target=rate_m, delayed_share=float(np.mean([v["delayed_share"] for v in vals])),
                      value_stopped=float(np.mean([v["value_stopped"] for v in vals]))))
tier[:] = base_tier

# ---------------- 5. sensitivity: which assumption moves SafePause most ----------------
sens = {}
vs = np.array([rr["P4"]["value_stopped"] for rr in runs])
for key in ["tc_enrol_senior", "tc_enrol_other", "tc_reply_30min", "officer_spots_high", "officer_spots_med",
            "officer_spots_flagged"]:
    xv = np.array([th[key] for th in thetas]); sens[key] = float(np.corrcoef(xv, vs)[0, 1])
xv = np.array([np.mean(list(th["tc_spots"].values())) for th in thetas]); sens["tc_spots(avg)"] = float(np.corrcoef(xv, vs)[0, 1])

# reason codes most often driving high-tier scam vs genuine flags
contrib = (Z * w)
def top_reasons(mask, k=6):
    c = contrib[mask]; top = np.argsort(-c, axis=1)[:, :3]
    cnt = np.bincount(top.ravel(), minlength=len(F)); o = np.argsort(-cnt)[:k]
    return {F[j]: int(cnt[j]) for j in o}
reasons = dict(scam_high=top_reasons(test & scam & (tier == 2)), genuine_high=top_reasons(test & ~scam & (tier == 2)),
               genuine_paused_kinds={kd: int(((D["kind"] == kd) & test & ~scam & (tier > 0)).sum())
                                     for kd in ["normal", "big_new", "fd_need", "family_emergency", "instalments"]},
               genuine_kinds_total={kd: int(((D["kind"] == kd) & test & ~scam).sum())
                                    for kd in ["normal", "big_new", "fd_need", "family_emergency", "instalments"]})

out = dict(model=dict(auc_seen=model_info["auc_test_seen_types"], auc_unseen=model_info["auc_test_unseen_types"],
                      t_med=t_med, t_high=t_high),
           summary=summary, sweep=sweep, sensitivity=sens, reasons=reasons, n_runs=N_RUNS,
           test_genuine_payments=int((test & ~scam).sum()), test_scam_payments=int((test & scam).sum()),
           test_episodes=int(len(set(ep[test & scam].tolist()))))
json.dump(out, open(os.path.join(OUT, "results.json"), "w"), indent=1)
for p in pols:
    s = summary[p]
    print(f"{p:13s} stopped {s['value_stopped']['median']*100:5.1f}% [{s['value_stopped']['p05']*100:4.1f}-{s['value_stopped']['p95']*100:4.1f}]"
          f"  victims {s['victims_fully_protected']['median']*100:5.1f}%"
          f"  genuine delayed {s['delayed_share']['median']*100:5.2f}%  per1000/mo {s['delayed_per_1000_cust_month']['median']:7.1f}"
          f"  delay {s['median_delay_min']['median']:5.1f}m")
print("AUC seen/unseen", round(model_info["auc_test_seen_types"], 3), round(model_info["auc_test_unseen_types"], 3))
print("by type P4", {k: round(v["median"], 2) for k, v in summary["P4"]["by_type"].items()})
print("by type P2", {k: round(v["median"], 2) for k, v in summary["P2"]["by_type"].items()})
print("officer", summary["P4"].get("officer_cases_per_lakh_cust_day"))
print("sens", sens); print("reasons", reasons)
