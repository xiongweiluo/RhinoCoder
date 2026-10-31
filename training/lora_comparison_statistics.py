"""Predeclared conservative paired CI from counts, never test material.

Stratified Clopper--Pearson plus Bonferroni; within-stratum iid sampling is
an explicit assumption. No bootstrap selection or adaptive sample expansion.
"""
import math

from plugin.rhino_listener.c5_research_native import require


def clopper_pearson(k, n, alpha):
    require(type(n) is int and 1 <= n <= 10000 and type(k) is int and 0 <= k <= n
            and 0 < alpha < 1, 'valid binomial counts required')
    def cdf(k, p):
        if p == 0: return 1.0
        if p == 1: return float(k >= n)
        return min(1., math.fsum(math.exp(math.lgamma(n+1)-math.lgamma(i+1)-math.lgamma(n-i+1)
            + i*math.log(p)+(n-i)*math.log1p(-p)) for i in range(k+1)))
    def inverse(k, target):
        lo, hi = 0., 1.
        for _ in range(80):
            mid = (lo + hi) / 2
            if cdf(k, mid) > target: lo = mid
            else: hi = mid
        return (lo + hi) / 2
    return [0. if k == 0 else inverse(k-1, 1-alpha/2),
            1. if k == n else inverse(k, alpha/2)]


def paired_interval(counts, strata, *, alpha=.05):
    """counts: each fixed layer has both, base_only, lora_only, neither.

    Incomplete/unknown results are ineligible; caller must first reconcile all
    fixed slots using outcome_summary and independent evidence review.
    """
    require(set(counts) == set(strata) and len(strata) > 0, 'all frozen strata required')
    total = sum(strata.values()); lower = upper = delta = 0.
    rows = {}
    for layer, n in strata.items():
        row = counts[layer]
        require(set(row) == {'both', 'base_only', 'lora_only', 'neither'}
                and all(type(x) is int and x >= 0 for x in row.values())
                and sum(row.values()) == n, 'complete fixed denominator required')
        positive = clopper_pearson(row['lora_only'], n, alpha/(2*len(strata)))
        negative = clopper_pearson(row['base_only'], n, alpha/(2*len(strata)))
        lo, hi = positive[0]-negative[1], positive[1]-negative[0]
        weight = n/total
        lower += weight*lo; upper += weight*hi
        delta += weight*(row['lora_only']-row['base_only'])/n
        rows[layer] = {'n': n, 'weight': weight, 'p10_ci': positive, 'p01_ci': negative, 'delta_ci': [lo, hi]}
    return {'method': 'stratified_CP_Bonferroni', 'confidence': 1-alpha,
        'delta_lora_minus_base': delta, 'interval': [max(-1., lower), min(1., upper)],
        'strata': rows, 'assumption': 'independent iid families within each fixed stratum',
        'execution_or_quality_approval': False}
