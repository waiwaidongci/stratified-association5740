"""冻结层顺序上的连续区间扫描（max-type 统计量，固定边际联合分布精确全局尾）。

统计量：在预先声明、顺序与计数均冻结的 K 个湿度层上，令每层 A 成功数 a_i 的
固定边际条件零假设均值为 mu_i = rA_i*c_i/n_i（有理数）。对所有连续区间
[i..j] 计算 |sum_{t=i..j}(a_t - mu_t)|，取最大值为扫描统计量 T；观察样本上
取得最大值的区间（含并列）一并报告。

全局精确证据：在与全层检验相同的固定边际联合分布（各层独立超几何的乘积）下，
枚举全部条件支持域组合，计算 P(T >= T_obs)。不做独立区间检验、不做 Bonferroni、
不用 Monte Carlo/模拟替代。

精确枚举用动态规划实现：状态为 (当前前缀 Q_k, 历史前缀最小值 mn_k, 历史前缀
最大值 mx_k)，其中 q_i = L*(a_i-mu_i)，L 为各 mu_i 约分分母的最小公倍数，
全部为整数；T = mx_K - mn_K（q_0=0 纳入极值），并列以整数精确比较。
预计内存超过 1 GiB 时在干跑计数阶段即拒绝计算。
"""
import math
from fractions import Fraction
from math import gcd

import numpy as np
from scipy.stats import hypergeom

# 单条 DP 状态（键三元组 + float 权重 + 字典槽位）的保守字节估计，用于内存守卫。
# 按 8x41 实测（244,321 状态、RSS 峰值约 200MiB）校准，留有余量。
_BYTES_PER_STATE = 420
# 干跑/加权两个字典同时存在的峰值倍数估计。
_PEAK_FACTOR = 2
MEMORY_LIMIT_BYTES = 1024 ** 3  # 1 GiB


def _lcm(a, b):
    return a // gcd(a, b) * b


def _layer_support(row):
    """返回该层超几何支持 a 的下界、上界与归一化 longdouble 概率。"""
    n = row['n']
    r = row['row_a']
    c = row['success_total']
    lo = max(0, r - (n - c))
    hi = min(r, c)
    support = np.arange(lo, hi + 1)
    logs = hypergeom.logpmf(support, n, c, r)
    pmf = np.exp(np.asarray(logs, dtype=np.longdouble))
    mass = pmf.sum()
    if not mass > 0 or not np.isfinite(mass):
        raise ValueError('超几何概率计算失败')
    pmf = pmf / mass
    return lo, hi, pmf


def _build_layers(rows):
    """冻结层顺序（rows 已按预先声明的 code 排序），构造整数缩放后的逐层支持。"""
    mus = [Fraction(t['row_a'] * t['success_total'], t['n']) for t in rows]
    scale = 1
    for mu in mus:
        scale = _lcm(scale, mu.denominator)
    layers = []
    for idx, (t, mu) in enumerate(zip(rows, mus)):
        lo, hi, pmf = _layer_support(t)
        scaled_mean = scale // mu.denominator * mu.numerator  # L*mu_i，精确整数
        steps = [(scale * a - scaled_mean, float(p)) for a, p in zip(range(lo, hi + 1), pmf)]
        layers.append({
            'index': idx,
            'code': t['code'],
            'name': t.get('name', t['code']),
            'lower': lo,
            'upper': hi,
            'support_count': hi - lo + 1,
            'mu': mu,
            'scaled_mean': scaled_mean,
            'steps': steps,
            'observed_a': t['a'],
            'observed_scaled_dev': scale * t['a'] - scaled_mean,
        })
    return layers, mus, scale


def _observed_scan(layers, mus):
    """观察样本上的扫描统计量与全部取得最大值的连续区间（含并列）。"""
    k = len(layers)
    deviations = [Fraction(layers[i]['observed_a']) - mus[i] for i in range(k)]
    best = None
    windows = []
    for start in range(k):
        acc = Fraction(0)
        for end in range(start, k):
            acc += deviations[end]
            value = abs(acc)
            if best is None or value > best:
                best = value
                windows = [(start, end)]
            elif value == best:
                windows.append((start, end))
    return best, windows, deviations


def _dry_run_count(layers):
    """只统计可达状态数（无权重），用于在加权 DP 前判定内存是否越限。"""
    states = {(0, 0, 0)}
    peak = 1
    for layer in layers:
        values = [step for step, _ in layer['steps']]
        nxt = set()
        for q, mn, mx in states:
            for step in values:
                q2 = q + step
                nxt.add((q2, min(mn, q2), max(mx, q2)))
        states = nxt
        peak = max(peak, len(nxt))
        estimated = peak * _BYTES_PER_STATE * _PEAK_FACTOR
        if estimated > MEMORY_LIMIT_BYTES:
            raise MemoryError(
                f"区间扫描在第{layer['index'] + 1}层后预计需要约"
                f"{estimated / 1024 ** 2:.1f}MiB状态内存，超过1GiB限额，拒绝计算"
            )
    return states, peak


def interval_scan_test(rows, alpha):
    """rows 为 cmh_algorithm.validate_tables 产出的、按冻结顺序排列的层。"""
    if not 2 <= len(rows) <= 8:
        raise ValueError('区间扫描需要2..8个预先声明的完整分层')
    layers, mus, scale = _build_layers(rows)
    k = len(layers)

    best, windows, deviations = _observed_scan(layers, mus)
    observed_scaled = best * scale  # 整数化的观察统计量，并列比较无浮点歧义

    # 干跑：先确认状态规模在 1 GiB 以内，再投入带权重的枚举。
    _, peak_states = _dry_run_count(layers)
    estimated_bytes = peak_states * _BYTES_PER_STATE * _PEAK_FACTOR

    # 加权 DP：在固定边际联合分布上传播每条路径的条件概率。
    dp = {(0, 0, 0): 1.0}
    for layer in layers:
        nxt = {}
        for (q, mn, mx), weight in dp.items():
            for step, p in layer['steps']:
                q2 = q + step
                key = (q2, min(mn, q2), max(mx, q2))
                nxt[key] = nxt.get(key, 0.0) + weight * p
        normalizer = sum(nxt.values())
        if not normalizer > 0 or not math.isfinite(normalizer):
            raise ValueError('区间扫描概率质量异常，计算未完成')
        dp = {key: w / normalizer for key, w in nxt.items()}

    statistic_mass = {}
    tail_mass = 0.0
    total_mass = 0.0
    for (q, mn, mx), weight in dp.items():
        t_scaled = mx - mn
        statistic_mass[t_scaled] = statistic_mass.get(t_scaled, 0.0) + weight
        total_mass += weight
        if t_scaled >= observed_scaled:
            tail_mass += weight

    log_tail = math.log(tail_mass) if tail_mass > 0 else None
    tail_numeric = float(tail_mass)
    distribution = []
    for t_scaled in sorted(statistic_mass):
        probability = statistic_mass[t_scaled]
        distribution.append({
            't_scaled': int(t_scaled),
            't_value': float(Fraction(int(t_scaled), scale)),
            'probability': float(probability),
            'log_probability': float(math.log(probability)) if probability > 0 else None,
            'in_tail': bool(t_scaled >= observed_scaled),
        })

    observed_window_details = []
    for start, end in windows:
        segment = sum(deviations[start:end + 1], Fraction(0))
        observed_window_details.append({
            'start_layer_index': start,
            'end_layer_index': end,
            'start_layer_code': layers[start]['code'],
            'end_layer_code': layers[end]['code'],
            'layer_count': end - start + 1,
            'deviation_numerator': segment.numerator,
            'deviation_denominator': segment.denominator,
            'deviation_value': float(segment),
        })

    return {
        'scan_type': 'frozen_order_contiguous_interval',
        'layer_order': [{'index': i, 'code': layers[i]['code'], 'name': layers[i]['name']} for i in range(k)],
        'layer_count': k,
        'scale_lcm': scale,
        'statistic_rule': (
            '冻结预先声明的层顺序与计数；对全部连续区间[i..j]取'
            '|Σ(a_t−E[a_t])|的最大值为统计量T，均值为固定边际条件均值（有理数）。'
        ),
        'tail_rule': (
            '同一固定边际联合分布（各层超几何乘积）下 P(T≥T观察) 的全局精确尾概率；'
            '整数缩放后精确判定并列。不是逐区间独立检验，不做多重性调整，无模拟。'
        ),
        'observed_statistic': str(best),
        'observed_statistic_numerator': best.numerator,
        'observed_statistic_denominator': best.denominator,
        'observed_statistic_scaled': int(observed_scaled),
        'selected_windows': observed_window_details,
        'selected_window_count': len(observed_window_details),
        'global_tail_p': tail_numeric if tail_numeric > 0 else None,
        'global_tail_p_log': log_tail,
        'global_tail_p_underflow': bool(tail_mass > 0 and tail_numeric == 0),
        'global_tail_p_display': np.format_float_scientific(
            np.longdouble(tail_mass), precision=8, unique=False
        ),
        'below_alpha': bool(tail_mass <= alpha),
        'alpha': alpha,
        'probability_sum': float(total_mass),
        'support_compositions': len(dp),
        'peak_states': peak_states,
        'estimated_memory_bytes': estimated_bytes,
        'estimated_memory_mib': round(estimated_bytes / 1048576, 1),
        'memory_limit_bytes': MEMORY_LIMIT_BYTES,
        'statistic_distribution': distribution,
        'layer_deviations': [{
            'index': i,
            'code': layers[i]['code'],
            'observed_a': layers[i]['observed_a'],
            'mean_numerator': mus[i].numerator,
            'mean_denominator': mus[i].denominator,
            'scaled_deviation': layers[i]['observed_scaled_dev'],
            'support_lower': layers[i]['lower'],
            'support_upper': layers[i]['upper'],
            'support_count': layers[i]['support_count'],
        } for i in range(k)],
        'numeric': '超几何logpmf→longdouble；纯Python字典DP枚举全部条件组合并逐层归一化；JSON保存double概率与log值。',
    }
