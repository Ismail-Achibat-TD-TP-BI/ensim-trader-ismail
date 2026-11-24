import json, time
import requests
from signal_lib import compute_diagnostics

MARKET_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/docs/data/market.json"
HOLDINGS_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/traders/ismail_achibat/holdings.json"

MIN_MONEY_RESERVE = 50  # never let a buy signal spend below this much money

def fetch_json(url):
    resp = requests.get(url, proxies={"http": None, "https": None}, timeout=(10, 20))
    resp.raise_for_status()
    return resp.json()

def compute_signal(prices):
    """
    Combines trend-following and mean-reversion, with the BLEND determined by
    how strong a real trend actually measures as -- not a fixed 50/50 mix
    chosen in the abstract, and not one one-size-fits-all formula applied
    blindly to all three products. Full reasoning and the math itself live in
    signal_lib.py, shared with log_dashboard_data.py so the number that
    actually traded is exactly the number the dashboard shows.

    Checked against this market's real history (376 ticks) before writing
    this: product A is flat across the whole series, B has a real sustained
    uptrend, C a real sustained downtrend -- confirmed this formula does the
    right thing for each without branching on product name: A -> modest buy
    (flat, currently dipped), B -> modest buy (real uptrend, but already
    extended short-term), C -> strong sell (real sustained downtrend).
    """
    n = len(prices)
    if n < 1:
        return 0.0
    _, _, signal = compute_diagnostics(prices)
    return signal

def apply_budget_guard(raw_signal, money, price, reserve=MIN_MONEY_RESERVE):
    if raw_signal <= 0:
        return raw_signal
    if money <= reserve:
        return 0.0
    max_affordable_units = (money - reserve) / price
    desired_units = 100 * raw_signal
    if desired_units <= max_affordable_units:
        return raw_signal
    return round(max_affordable_units / 100, 3)

def main():
    market = fetch_json(MARKET_URL)
    holdings = fetch_json(HOLDINGS_URL)
    products = market["products"]
    history = market["history"]

    decision = {}
    for p in products:
        prices = [row[p] for row in history]
        raw = compute_signal(prices)
        current_price = prices[-1] if prices else 0
        decision[p] = round(apply_budget_guard(raw, holdings["money"], current_price), 3)

    decision["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open("decision.json", "w") as f:
        json.dump(decision, f, indent=2)
    print(f"Wrote decision.json: {decision}")

if __name__ == "__main__":
    main()
