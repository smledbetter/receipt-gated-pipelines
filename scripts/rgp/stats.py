"""Small statistics helpers. All tests are exact."""
import math

from scipy.stats import binomtest, fisher_exact, mannwhitneyu


def wilson(k, n, z=1.959964):
    """Wilson score interval for a proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def fisher(k1, n1, k2, n2):
    """Two-sided Fisher exact p for k1/n1 vs k2/n2."""
    return fisher_exact([[k1, n1 - k1], [k2, n2 - k2]])[1]


def mcnemar_exact(b, c):
    """Exact McNemar p from the discordant counts b (yes/no) and c (no/yes)."""
    n = b + c
    if n == 0:
        return 1.0
    return binomtest(min(b, c), n, 0.5).pvalue


def mannwhitney(a, b):
    try:
        return mannwhitneyu(a, b, alternative="two-sided").pvalue
    except ValueError:
        return float("nan")


def rate(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({k / n:.0%}, CI {lo:.0%}-{hi:.0%})" if n else "n/a"
