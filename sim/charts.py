"""Charts for the deck. Transparent background, light text: they sit on the dark K! Hacks template."""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
R = json.load(open(os.path.join(HERE, "results", "results.json")))
OUT = os.path.join(HERE, "charts"); os.makedirs(OUT, exist_ok=True)
S = R["summary"]
LIME, WHITE, GREY, DIM, AMBER = "#D9FF43", "#F2F2F2", "#9AA3AE", "#5B6573", "#FFB547"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 15, "text.color": WHITE, "axes.labelcolor": WHITE,
                     "xtick.color": WHITE, "ytick.color": WHITE, "axes.edgecolor": GREY})

def style(ax):
    for s in ["top", "right"]: ax.spines[s].set_visible(False)
    ax.grid(axis="y", color=DIM, alpha=.35, lw=.8); ax.set_axisbelow(True)

# ---- 1. main trade-off chart ----
fig, ax = plt.subplots(figsize=(8.2, 5.2))
sw = R["sweep"]
ax.plot([p["delayed_share"] * 100 for p in sw], [p["value_stopped"] * 100 for p in sw], color=LIME, lw=2)
pts = [("P2", "1-hour lag on every payment\nabove ₹10,000 (RBI option 1)", AMBER),
       ("P3", "Trusted person for 70+ above\n₹50,000 (RBI option 2)", GREY),
       ("P4", "SafePause, setting we chose", LIME)]
for key, lab, col in pts:
    x = S[key]["delayed_share"]["median"] * 100; y = S[key]["value_stopped"]
    ax.errorbar(x, y["median"] * 100, yerr=[[(y["median"] - y["p05"]) * 100], [(y["p95"] - y["median"]) * 100]],
                fmt="o", ms=9, color=col, ecolor=col, capsize=4, lw=1.6, zorder=5)
off = {"P2": (-2.75, 12), "P3": (0.28, -3), "P4": (0.25, -11)}
for key, lab, col in pts:
    x = S[key]["delayed_share"]["median"] * 100; y = S[key]["value_stopped"]["median"] * 100
    dx, dy = off[key]; ax.annotate(lab, (x, y), (x + dx, y + dy), fontsize=12.5, color=col)
ax.annotate("Other SafePause settings", (2.4, 89), (2.4, 94), fontsize=12, color=LIME)
ax.set_xlabel("Genuine payments delayed (%)")
ax.set_ylabel("Scam money stopped (%)")
ax.set_xlim(-0.1, 5.4); ax.set_ylim(0, 100); style(ax)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "tradeoff.png"), dpi=220, transparent=True); plt.close(fig)

# ---- 2. by scam type ----
types = [("digital_arrest", "Digital\narrest"), ("investment", "Fake\ninvestment"), ("kyc_call", "Fake KYC /\nrefund call"),
         ("small_ticket", "Small QR /\nmarketplace"), ("task_job", "Task / job\n(unseen)"), ("relative_voice", "Fake relative\n(unseen)")]
fig, ax = plt.subplots(figsize=(9.2, 4.6))
import numpy as np
xs = np.arange(len(types)); wdt = .26
for j, (key, lab, col) in enumerate([("P2", "1-hour lag", AMBER), ("P1", "Rules + warning pop-up", GREY), ("P4", "SafePause", LIME)]):
    vals = [S[key]["by_type"][t]["median"] * 100 for t, _ in types]
    b = ax.bar(xs + (j - 1) * wdt, vals, wdt, color=col, label=lab)
    if key == "P4":
        for xi, v in zip(xs, vals): ax.text(xi + wdt, v + 2, f"{v:.0f}", ha="center", fontsize=12, color=LIME)
ax.set_xticks(xs); ax.set_xticklabels([l for _, l in types], fontsize=12)
ax.set_ylabel("Scam money stopped (%)"); ax.set_ylim(0, 100); style(ax)
ax.legend(frameon=False, fontsize=12, ncol=3, loc="upper center", bbox_to_anchor=(.5, 1.13))
fig.tight_layout(); fig.savefig(os.path.join(OUT, "by_type.png"), dpi=220, transparent=True); plt.close(fig)

# ---- 3. what each part adds ----
fig, ax = plt.subplots(figsize=(6.4, 3.6))
rows = [("P4_open_hold", "Hold shown openly to\nthe customer", GREY), ("P4_no_tc", "Silent pause,\nno trusted contact", GREY),
        ("P4", "Full SafePause", LIME)]
for i, (k, lab, col) in enumerate(rows):
    v = S[k]["value_stopped"]["median"] * 100
    ax.barh(i, v, color=col, height=.6); ax.text(v + 1.5, i, f"{v:.0f}%", va="center", fontsize=14, color=col)
ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[1] for r in rows], fontsize=12)
ax.set_xlim(0, 100); ax.set_xlabel("Scam money stopped (%)")
for s in ["top", "right"]: ax.spines[s].set_visible(False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "ablation.png"), dpi=220, transparent=True); plt.close(fig)
print("charts written to", OUT)
