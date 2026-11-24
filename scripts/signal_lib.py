import statistics

# Shared between algorithm.py (the live decision) and log_dashboard_data.py
# (the dashboard's product-level-signal history) so the two can never drift
# apart -- the number that actually traded is exactly the number the
# dashboard shows, computed once, not re-derived twice.

MIN_HISTORY = 15
Z_WINDOW = 40
TREND_WEIGHT = 0.5
REVERSION_WEIGHT = 0.5
SCALE_DIVISOR = 3.0

def compute_diagnostics(prices):
    """Returns (trend_z, z, signal) -- see algorithm.py's compute_signal for
    the full reasoning. trend_z: the product's whole-history OLS trend,
    expressed in standard-deviation units (how many std devs has this trend
    line moved end to end). z: how far the current price sits from its own
    recent (Z_WINDOW-tick) mean, in std-dev units."""
    n = len(prices)
    if n < MIN_HISTORY:
        return 0.0, 0.0, 0.0

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
    signal = max(-1.0, min(1.0, round(raw, 3)))
    return round(trend_z, 3), round(z, 3), signal

def reason_for(trend_z, z):
    """One deterministic, templated sentence from the real numbers -- never
    an LLM narrating a decision, per this course's human-in-the-loop
    principle applied to a decision log instead of a job-application tracker."""
    if abs(trend_z) < 0.3:
        return f"flat/range-bound (trend_z={trend_z:+.2f}) -> trading the recent dip/rally only (z={z:+.2f})"
    direction = "uptrend" if trend_z > 0 else "downtrend"
    extended = abs(z) > 0.5 and (z > 0) == (trend_z > 0)
    sizing = "already extended, sized down" if extended else "good entry point"
    return f"real {direction} (trend_z={trend_z:+.2f}), {sizing} (z={z:+.2f})"
