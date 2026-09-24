"""双探头保守复核：两条分段线性致死速率曲线的下包络积分。

业务约定：
- 每支探头的采样各自遵守与单探头相同的校验，且两组均从 0 秒开始、
  结束于同一秒；
- 原梯形法隐含"致死速率在相邻采样点间分段线性"的假设，因此在两组
  采样时刻的并集上，对每条速率曲线做分段线性插值；
- 质检员按每一时刻较低的致死速率形成保守结论：若两条速率线在区间
  内部交换高低，须在交点拆段，再对下包络逐段梯形积分；
- 保守总量是逐时刻取低的积分，必然不高于任一探头各自总量，因此
  不能简单取两份总 F₀ 的较小值代替；
- 放行判定只使用未舍入的保守总量与原门槛（3.00 min）比较。
"""

from __future__ import annotations

from dataclasses import dataclass

from .lethality import SECONDS_PER_MINUTE, THRESHOLD_MINUTES, lethality_rate

SOURCE_A = "A"
SOURCE_B = "B"
SOURCE_BOTH = "both"  # 两探头速率整段重合


@dataclass(frozen=True)
class ConservativeSegment:
    """下包络的一段：区间内保守速率始终来自同一探头（或两探头一致）。"""

    index: int  # 1-based 段号
    start_time: float  # 秒；区间内部交点拆段时可能不是整数
    end_time: float
    source: str  # "A" / "B" / "both"
    start_rate: float  # 段起点保守速率（未舍入）
    end_rate: float
    duration_seconds: float
    contribution: float  # 未舍入的段贡献（分钟）


@dataclass(frozen=True)
class DualResult:
    segments: list[ConservativeSegment]
    conservative_total: float  # 未舍入的保守总量（分钟），放行判定唯一依据
    probe_a_total: float  # 探头A 各自全程梯形积分（未舍入，仅作对照）
    probe_b_total: float
    series_a: list[tuple[float, float]]  # (秒, 速率)，探头A 采样点处的速率折线
    series_b: list[tuple[float, float]]
    passed: bool
    shortfall: float | None  # 未达标时距门槛的未舍入差额；达标为 None


def _rate_series(points: list[tuple[int, float]]) -> list[tuple[float, float]]:
    """(time, temperature) 采样序列 → (time, rate) 速率折线。"""
    return [(float(t), lethality_rate(temp)) for t, temp in points]


def _interpolate(series: list[tuple[float, float]], t: float) -> float:
    """分段线性速率曲线在时刻 t 的取值（t 必在曲线定义域内）。"""
    for (t0, r0), (t1, r1) in zip(series, series[1:]):
        if t0 <= t <= t1:
            # 恰为采样点时直接返回该点速率：共有采样时刻上两探头
            # 各自直接求值，保证相同温度得到逐位相等的速率
            if t == t0:
                return r0
            if t == t1:
                return r1
            return r0 + (r1 - r0) * (t - t0) / (t1 - t0)
    raise ValueError(f"时刻 {t} 超出速率曲线定义域")


def _trapezoid_total(series: list[tuple[float, float]]) -> float:
    """单条速率折线的全程梯形积分（分钟），等价于原梯形法总量。"""
    return sum(
        (r0 + r1) / 2.0 * (t1 - t0) / SECONDS_PER_MINUTE
        for (t0, r0), (t1, r1) in zip(series, series[1:])
    )


def compute_dual(
    points_a: list[tuple[int, float]], points_b: list[tuple[int, float]]
) -> DualResult:
    """对两组 (time_seconds, temperature_c) 采样求下包络保守积分。"""
    if len(points_a) < 2 or len(points_b) < 2:
        raise ValueError("每组至少需要两个采样点")
    if points_a[0][0] != 0 or points_b[0][0] != 0:
        raise ValueError("两组采样均须从 0 秒开始")
    if points_a[-1][0] != points_b[-1][0]:
        raise ValueError("两组采样须结束于同一秒")

    series_a = _rate_series(points_a)
    series_b = _rate_series(points_b)
    # 两组采样时刻的并集：每条速率曲线在其上都是分段线性的
    times = sorted({t for t, _ in series_a} | {t for t, _ in series_b})
    grid_a = [_interpolate(series_a, t) for t in times]
    grid_b = [_interpolate(series_b, t) for t in times]

    segments: list[ConservativeSegment] = []

    def append_segment(
        start: float, end: float, source: str, start_rate: float, end_rate: float
    ) -> None:
        contribution = (start_rate + end_rate) / 2.0 * (end - start) / SECONDS_PER_MINUTE
        segments.append(
            ConservativeSegment(
                index=len(segments) + 1,
                start_time=start,
                end_time=end,
                source=source,
                start_rate=start_rate,
                end_rate=end_rate,
                duration_seconds=end - start,
                contribution=contribution,
            )
        )

    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        a0, a1 = grid_a[i], grid_a[i + 1]
        b0, b1 = grid_b[i], grid_b[i + 1]
        # 差值 d = rateA - rateB 在区间上同为线性，只看端点符号
        d0, d1 = a0 - b0, a1 - b1

        if d0 == 0.0 and d1 == 0.0:
            # 两端速率都相等 → 两条线整段重合
            append_segment(t0, t1, SOURCE_BOTH, a0, a1)
        elif (d0 < 0.0 < d1) or (d1 < 0.0 < d0):
            # 区间内部交换高低：求唯一交点并拆段
            fraction = d0 / (d0 - d1)
            cross_t = t0 + fraction * (t1 - t0)
            cross_rate = a0 + fraction * (a1 - a0)
            if d0 < 0.0:  # 前半段 A 低，后半段 B 低
                append_segment(t0, cross_t, SOURCE_A, a0, cross_rate)
                append_segment(cross_t, t1, SOURCE_B, cross_rate, b1)
            else:
                append_segment(t0, cross_t, SOURCE_B, b0, cross_rate)
                append_segment(cross_t, t1, SOURCE_A, cross_rate, a1)
        elif d0 <= 0.0 and d1 <= 0.0:
            # 全程 A 不高于 B（端点可能恰好相等 → 端点换源，无需拆段）
            append_segment(t0, t1, SOURCE_A, a0, a1)
        else:
            append_segment(t0, t1, SOURCE_B, b0, b1)

    conservative_total = sum(s.contribution for s in segments)
    threshold = float(THRESHOLD_MINUTES)
    # 放行只用未舍入的保守总量与原门槛比较，不做任何舍入
    passed = conservative_total >= threshold
    return DualResult(
        segments=segments,
        conservative_total=conservative_total,
        probe_a_total=_trapezoid_total(series_a),
        probe_b_total=_trapezoid_total(series_b),
        series_a=series_a,
        series_b=series_b,
        passed=passed,
        shortfall=None if passed else threshold - conservative_total,
    )
