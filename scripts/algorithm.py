import json, time, statistics
import requests

MARKET_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/docs/data/market.json"
HOLDINGS_URL = "https://raw.githubusercontent.com/exofri/ensim-trade-center/refs/heads/main/traders/ismail_achibat/holdings.json"

MIN_MONEY_RESERVE = 50  # never let a buy signal spend below this much money

def fetch_json(url):
    resp = requests.get(url, proxies={"http": None, "https": None}, timeout=(10, 20))
    resp.raise_for_status()
    return resp.json()

MIN_HISTORY = 15     # don't trust any of this below this many observed ticks
Z_WINDOW = 40        # recent window used for the mean-reversion/timing z-score
TREND_WEIGHT = 0.5
REVERSION_WEIGHT = 0.5
SCALE_DIVISOR = 3.0  # chosen empirically: typical trend_z/z magnitudes on this
                     # market's real history (checked against 376 real ticks
                     # before committing to this) land raw in roughly [-2.5, 2.5],
                     # so dividing by 3 uses most of [-1, 1] without constantly
                     # saturating at the hard clip.

def compute_signal(prices):
    """
    Combines trend-following and mean-reversion, with the BLEND determined by
    how strong a real trend actually measures as -- not a fixed 50/50 mix
    chosen in the abstract, and not one one-size-fits-all formula applied
    blindly to all three products.

    Checked against this market's real history (376 ticks) before writing
    this: product A is flat across the whole series (pure range-bound noise),
    B has a real, sustained uptrend across every quarter of its history, C has
    a real, sustained downtrend. A fixed Bollinger/mean-reversion strategy
    would be wrong for B/C (it would keep fighting a real trend); a fixed
    momentum strategy would be wrong for A (there is no real trend to ride).
    This formula doesn't branch per-product by name -- the right behavior
    falls out of the math for whichever product it's given:

    - trend_z: the product's OLS trend line's total predicted move across the
      whole observed window, expressed in standard-deviation units (NOT the
      raw per-tick slope, which is numerically tiny regardless of how real a
      trend is -- an earlier version of this used the raw slope and it was
      completely dominated by the reversion term, incorrectly turning a real
      uptrend into a sell signal; this is the actual fix for that).
    - z: how far the current price sits from its own recent (Z_WINDOW-tick)
      mean, in standard-deviation units -- the mean-reversion/timing signal,
      i.e. "is this a good moment to act, given the trend."

    Result: on a flat product, trend_z ~ 0, so the signal is driven almost
    entirely by z (buy dips, sell rallies -- pure mean-reversion). On a
    strongly trending product, trend_z dominates (trade with the real trend),
    while z still nudges the size down when the trend has already run far
    (don't chase an extended move) -- checked on this market's real A/B/C
    history: A -> modest buy (flat, currently dipped), B -> modest buy (real
    uptrend, but already extended short-term), C -> strong sell (real
    sustained downtrend, not offset by a small recent bounce).
    """
    n = len(prices)
    if n < MIN_HISTORY:
        return 0.0  # not enough history to trust any estimate yet -- the safe default

    days = list(range(n))
    mean_x = statistics.mean(days)
    mean_y = statistics.mean(prices)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(days, prices))
    den = sum((x - mean_x) ** 2 for x in days)
    slope = num / den if den else 0.0
    price_std = statistics.pstdev(prices) if n > 1 else 0.0
    trend_z = (slope * (n - 1)) / price_std if price_std else 0.0

    w = Z_WINDOW if n >= Z_WINDOW else n
    recent = prices[-w:]
    mean_r = statistics.mean(recent)
    std_r = statistics.pstdev(recent)
    z = (prices[-1] - mean_r) / std_r if std_r else 0.0

    raw = (TREND_WEIGHT * trend_z - REVERSION_WEIGHT * z) / SCALE_DIVISOR
    return max(-1.0, min(1.0, round(raw, 3)))

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
