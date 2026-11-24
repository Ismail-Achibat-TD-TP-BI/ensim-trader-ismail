import json, os, time
import requests
from signal_lib import compute_diagnostics, reason_for

MARKET_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/docs/data/market.json"
HOLDINGS_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/traders/ismail_achibat/holdings.json"
LEADERBOARD_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/docs/data/leaderboard.json"
HOLDINGS_BASE = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/traders/{id}/holdings.json"

PERF_PATH = "docs/data/performance_history.json"
SIGNAL_PATH = "docs/data/signal_history.json"
DECISION_LOG_PATH = "docs/data/decision_log.json"

def fetch_json(url):
    resp = requests.get(url, proxies={"http": None, "https": None}, timeout=(10, 20))
    resp.raise_for_status()
    return resp.json()

def total_value(holdings, prices):
    return round(holdings["money"] + sum(holdings["products"][p] * prices[p] for p in prices), 2)

def load_or_init(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default

def main():
    market = fetch_json(MARKET_URL)
    holdings = fetch_json(HOLDINGS_URL)
    leaderboard = fetch_json(LEADERBOARD_URL)["leaderboard"]
    products = market["products"]
    history = market["history"]
    current_prices = {p: history[-1][p] for p in products}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tick = history[-1]["t"]

    # --- Performance vs. baselines: the organizer only ever gives a CURRENT
    # snapshot (leaderboard.json, each trader's holdings.json) -- there is no
    # historical portfolio-value feed for anyone, baselines included. So this
    # is the pipeline's own acquisition step: fetch the 3 real baseline
    # traders' current holdings (flagged "baseline": true in leaderboard.json,
    # not hardcoded by name) every run, value them at the current real price,
    # and append -- building the history ourselves, the same pattern TD2 used
    # for a feed with no archive of its own.
    baseline_ids = [t["id"] for t in leaderboard if t.get("baseline")]
    baseline_values = {}
    for bid in baseline_ids:
        bh = fetch_json(HOLDINGS_BASE.format(id=bid))
        baseline_values[bid] = total_value(bh, current_prices)

    perf = load_or_init(PERF_PATH, {"baseline_ids": baseline_ids, "points": []})
    if perf["points"] and perf["points"][-1]["t"] == tick:
        print(f"Tick {tick} already logged (market hasn't ticked since last run) -- skipping, not duplicating.")
        return
    perf["points"].append({
        "t": tick, "timestamp": now,
        "me": total_value(holdings, current_prices),
        **baseline_values,
    })
    with open(PERF_PATH, "w") as f:
        json.dump(perf, f, indent=2)

    # --- Product-level signal history + decision log ---
    sig_hist = load_or_init(SIGNAL_PATH, {"points": []})
    dec_hist = load_or_init(DECISION_LOG_PATH, {"entries": []})
    decision = json.load(open("decision.json"))

    sig_row = {"t": tick, "timestamp": now}
    reasons = {}
    for p in products:
        prices = [row[p] for row in history]
        trend_z, z, signal = compute_diagnostics(prices)
        sig_row[p] = {"trend_z": trend_z, "z": z, "signal": signal, "price": current_prices[p]}
        reasons[p] = reason_for(trend_z, z)
    sig_hist["points"].append(sig_row)
    with open(SIGNAL_PATH, "w") as f:
        json.dump(sig_hist, f, indent=2)

    dec_hist["entries"].append({
        "t": tick, "timestamp": now,
        "decision": {p: decision[p] for p in products},
        "reason": reasons,
    })
    with open(DECISION_LOG_PATH, "w") as f:
        json.dump(dec_hist, f, indent=2)

    print(f"Logged tick {tick}: me={perf['points'][-1]['me']}, "
          f"baselines={baseline_values}, decision={decision}")

if __name__ == "__main__":
    main()
