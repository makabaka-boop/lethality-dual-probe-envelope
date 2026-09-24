"""双探头保守复核计算测试。

两类互相独立的验证手段：
1. 解析交点样例：手算交点位置、拆段来源与下包络贡献，精确比对；
2. 独立细分积分预言机：用细网格数值积分 min(rateA, rateB) 作为
   参照，验证主实现（解析拆段）在换源、重合、端点换源等形态下
   都收敛到同一保守总量。
"""

from decimal import Decimal

import pytest

from app.dual import compute_dual
from app.lethality import lethality_rate

R110 = lethality_rate(110.0)
R115 = lethality_rate(115.0)
R120 = lethality_rate(120.0)
R127 = lethality_rate(127.0)
R130 = lethality_rate(130.0)


def oracle_conservative(
    points_a: list[tuple[int, float]],
    points_b: list[tuple[int, float]],
    step_seconds: float = 0.005,
) -> float:
    """独立预言机：细网格梯形数值积分逐时刻 min(rateA, rateB)。

    与主实现路径完全独立：不找交点、不拆段，只在细密网格上对两条
    分段线性速率曲线逐点取低后积分，用于交叉验证保守总量。
    """

    def curve(points):
        series = [(float(t), lethality_rate(temp)) for t, temp in points]

        def rate_at(t: float) -> float:
            for (t0, r0), (t1, r1) in zip(series, series[1:]):
                if t0 <= t <= t1:
                    if t1 == t0:
                        return r0
                    return r0 + (r1 - r0) * (t - t0) / (t1 - t0)
            raise AssertionError(f"t={t} 超出定义域")

        return rate_at

    rate_a, rate_b = curve(points_a), curve(points_b)
    end = float(points_a[-1][0])
    total = 0.0
    t = 0.0
    while t < end - 1e-12:
        t2 = min(t + step_seconds, end)
        total += (
            (min(rate_a(t), rate_b(t)) + min(rate_a(t2), rate_b(t2)))
            / 2.0
            * (t2 - t)
            / 60.0
        )
        t = t2
    return total


class TestInteriorCrossing:
    """换源：两条速率线在区间内部交换高低，须在交点拆段。"""

    # A 前低后高、B 前高后低，关于中点对称 → 交点恰在 90 s
    POINTS_A = [(0, 115.0), (60, 115.0), (120, 127.0), (180, 127.0)]
    POINTS_B = [(0, 127.0), (60, 127.0), (120, 115.0), (180, 115.0)]

    def test_segments_split_at_analytic_crossing(self):
        result = compute_dual(self.POINTS_A, self.POINTS_B)
        assert len(result.segments) == 4

        first, second, third, fourth = result.segments
        # [0,60] A 全程较低；[60,90] A 仍低；交点 90 s；之后 B 较低
        assert (first.start_time, first.end_time, first.source) == (0.0, 60.0, "A")
        assert (second.start_time, second.end_time, second.source) == (60.0, 90.0, "A")
        assert (third.start_time, third.end_time, third.source) == (90.0, 120.0, "B")
        assert (fourth.start_time, fourth.end_time, fourth.source) == (120.0, 180.0, "B")

        # 交点速率：两条线在中点相交，解析值为两端速率的平均
        cross_rate = (R115 + R127) / 2.0
        assert second.end_rate == pytest.approx(cross_rate)
        assert third.start_rate == pytest.approx(cross_rate)

    def test_contributions_match_hand_computed_envelope(self):
        result = compute_dual(self.POINTS_A, self.POINTS_B)
        cross_rate = (R115 + R127) / 2.0
        expected = [
            R115 * 1.0,  # [0,60] 恒温 115 °C，1 min
            (R115 + cross_rate) / 2.0 * 0.5,  # [60,90] 梯形，0.5 min
            (cross_rate + R115) / 2.0 * 0.5,  # [90,120] 梯形，0.5 min
            R115 * 1.0,  # [120,180] 恒温 115 °C，1 min
        ]
        assert [s.contribution for s in result.segments] == pytest.approx(expected)
        assert result.conservative_total == pytest.approx(sum(expected))

    def test_conservative_total_is_below_each_probe_total(self):
        # 关键业务断言：保守总量 ≠ 两份总量的较小值，而是更保守（更低）
        result = compute_dual(self.POINTS_A, self.POINTS_B)
        assert result.probe_a_total == pytest.approx(result.probe_b_total)
        assert result.conservative_total < min(
            result.probe_a_total, result.probe_b_total
        )

    def test_matches_fine_grid_oracle(self):
        result = compute_dual(self.POINTS_A, self.POINTS_B)
        oracle = oracle_conservative(self.POINTS_A, self.POINTS_B)
        assert result.conservative_total == pytest.approx(oracle, rel=1e-6)

    def test_swapping_probes_swaps_sources_but_not_total(self):
        forward = compute_dual(self.POINTS_A, self.POINTS_B)
        swapped = compute_dual(self.POINTS_B, self.POINTS_A)
        assert swapped.conservative_total == pytest.approx(forward.conservative_total)
        swap = {"A": "B", "B": "A", "both": "both"}
        assert [s.source for s in swapped.segments] == [
            swap[s.source] for s in forward.segments
        ]


class TestCoincidentCurves:
    """重合：两条速率线整段或部分相等。"""

    def test_identical_samples_mark_all_segments_both(self):
        points = [(0, 118.0), (45, 123.5), (90, 121.1), (180, 126.0)]
        result = compute_dual(points, points)
        assert [s.source for s in result.segments] == ["both"] * 3
        # 重合时保守总量与任一探头各自总量一致
        assert result.conservative_total == pytest.approx(result.probe_a_total)
        assert result.conservative_total == pytest.approx(result.probe_b_total)

    def test_partial_overlap_only_marks_overlapping_interval(self):
        points_a = [(0, 120.0), (60, 130.0), (120, 120.0)]
        points_b = [(0, 120.0), (60, 130.0), (120, 110.0)]
        result = compute_dual(points_a, points_b)
        # [0,60] 两线重合；[60,120] B 一路低于 A
        assert [s.source for s in result.segments] == ["both", "B"]
        assert result.segments[1].end_rate == pytest.approx(lethality_rate(110.0))

    def test_matches_oracle(self):
        points = [(0, 118.0), (45, 123.5), (90, 121.1), (180, 126.0)]
        result = compute_dual(points, points)
        assert result.conservative_total == pytest.approx(
            oracle_conservative(points, points), rel=1e-6
        )


class TestEndpointSwitch:
    """端点换源：两条线恰在采样时刻相等，换源发生在网格点上，不拆段。"""

    # t=60 时两探头同为 120 °C；之前 B 低，之后 A 低
    POINTS_A = [(0, 130.0), (60, 120.0), (120, 110.0)]
    POINTS_B = [(0, 110.0), (60, 120.0), (120, 130.0)]

    def test_switch_at_shared_sample_time_without_splitting(self):
        result = compute_dual(self.POINTS_A, self.POINTS_B)
        assert len(result.segments) == 2
        first, second = result.segments
        assert (first.start_time, first.end_time, first.source) == (0.0, 60.0, "B")
        assert (second.start_time, second.end_time, second.source) == (60.0, 120.0, "A")
        # 换源点速率恰为 120 °C 的致死速率
        assert first.end_rate == pytest.approx(R120)
        assert second.start_rate == pytest.approx(R120)

    def test_contributions_are_hand_computable(self):
        result = compute_dual(self.POINTS_A, self.POINTS_B)
        expected_each = (R110 + R120) / 2.0 * 1.0  # 每段 60 s = 1 min
        assert result.segments[0].contribution == pytest.approx(expected_each)
        assert result.segments[1].contribution == pytest.approx(expected_each)
        assert result.conservative_total == pytest.approx(R110 + R120)

    def test_matches_oracle(self):
        result = compute_dual(self.POINTS_A, self.POINTS_B)
        assert result.conservative_total == pytest.approx(
            oracle_conservative(self.POINTS_A, self.POINTS_B), rel=1e-6
        )


class TestUnionGridInterpolation:
    """采样时刻不一致：在并集网格上按分段线性插值取值。"""

    def test_segments_follow_union_of_sample_times(self):
        points_a = [(0, 121.1), (60, 121.1), (120, 121.1)]
        points_b = [(0, 100.0), (30, 100.0), (90, 100.0), (120, 100.0)]
        result = compute_dual(points_a, points_b)
        # 并集 {0,30,60,90,120}；B 全程远低于 A，保守曲线即 B
        assert [(s.start_time, s.end_time) for s in result.segments] == [
            (0.0, 30.0),
            (30.0, 60.0),
            (60.0, 90.0),
            (90.0, 120.0),
        ]
        assert all(s.source == "B" for s in result.segments)
        assert result.conservative_total == pytest.approx(result.probe_b_total)

    def test_interpolated_crossing_matches_oracle(self):
        # 两组采样时刻错开，交点落在插值段内部
        points_a = [(0, 112.0), (50, 112.0), (100, 128.0), (150, 128.0)]
        points_b = [(0, 126.0), (40, 126.0), (110, 114.0), (150, 114.0)]
        result = compute_dual(points_a, points_b)
        assert result.conservative_total == pytest.approx(
            oracle_conservative(points_a, points_b), rel=1e-6
        )
        sources = {s.source for s in result.segments}
        assert sources == {"A", "B"}  # 确实发生了换源

    def test_segments_tile_the_full_interval_without_gaps(self):
        points_a = [(0, 112.0), (50, 112.0), (100, 128.0), (150, 128.0)]
        points_b = [(0, 126.0), (40, 126.0), (110, 114.0), (150, 114.0)]
        result = compute_dual(points_a, points_b)
        assert result.segments[0].start_time == 0.0
        assert result.segments[-1].end_time == 150.0
        for prev, curr in zip(result.segments, result.segments[1:]):
            assert curr.start_time == pytest.approx(prev.end_time)
        assert sum(s.contribution for s in result.segments) == pytest.approx(
            result.conservative_total
        )


class TestThresholdDecision:
    """临界判定：放行只用未舍入的保守总量与 3.00 min 比较。"""

    def test_exactly_three_minutes_passes(self):
        points = [(0, 121.1), (60, 121.1), (120, 121.1), (180, 121.1)]
        result = compute_dual(points, points)
        assert result.conservative_total == pytest.approx(3.0)
        assert result.passed is True
        assert result.shortfall is None

    def test_unrounded_total_just_below_threshold_fails(self):
        # 未舍入保守总量 2.9999999 < 3.00：即便四舍五入后为 3.00 也不放行。
        # 这是双探头与单探头口径的关键差异：判定不做任何舍入。
        import math

        rate = 2.9999999 / 3.0
        temperature = 121.1 + 10.0 * math.log10(rate)
        points = [(0, temperature), (60, temperature), (120, temperature), (180, temperature)]
        result = compute_dual(points, points)
        assert result.conservative_total == pytest.approx(2.9999999)
        assert result.passed is False
        assert result.shortfall == pytest.approx(3.0 - 2.9999999)

    def test_unrounded_total_just_above_threshold_passes(self):
        import math

        rate = 3.0000001 / 3.0
        temperature = 121.1 + 10.0 * math.log10(rate)
        points = [(0, temperature), (60, temperature), (120, temperature), (180, temperature)]
        result = compute_dual(points, points)
        assert result.passed is True
        assert result.shortfall is None

    def test_decision_follows_conservative_not_individual_totals(self):
        # 各自总量都达标，但逐时刻取低后的保守总量不达标 → 不放行
        points_a = [(0, 115.0), (60, 115.0), (120, 127.0), (180, 127.0)]
        points_b = [(0, 127.0), (60, 127.0), (120, 115.0), (180, 115.0)]
        result = compute_dual(points_a, points_b)
        assert result.probe_a_total > 3.0
        assert result.probe_b_total > 3.0
        assert result.conservative_total < 3.0
        assert result.passed is False


class TestOracleAgreementOnRandomSamples:
    """随机错时采样：主实现与独立细分积分预言机一致。"""

    def test_randomized_samples_match_oracle(self):
        import random

        rng = random.Random(20260924)
        for _ in range(30):
            def random_points():
                times = [0]
                while times[-1] < 180:
                    times.append(min(times[-1] + rng.randint(15, 60), 180))
                return [(t, rng.uniform(100.0, 140.0)) for t in times]

            points_a, points_b = random_points(), random_points()
            result = compute_dual(points_a, points_b)
            oracle = oracle_conservative(points_a, points_b)
            assert result.conservative_total == pytest.approx(oracle, rel=1e-6)
            # 保守总量永不超过任一探头各自总量
            assert result.conservative_total <= result.probe_a_total + 1e-9
            assert result.conservative_total <= result.probe_b_total + 1e-9


class TestPreconditions:
    def test_mismatched_end_times_rejected(self):
        with pytest.raises(ValueError):
            compute_dual([(0, 121.1), (60, 121.1)], [(0, 121.1), (90, 121.1)])

    def test_too_few_points_rejected(self):
        with pytest.raises(ValueError):
            compute_dual([(0, 121.1)], [(0, 121.1), (60, 121.1)])
