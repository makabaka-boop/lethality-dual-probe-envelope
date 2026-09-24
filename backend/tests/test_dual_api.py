"""双探头复核接口测试：响应结构、换源拆段、校验定位与原接口兼容性。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def dual_payload() -> dict:
    """换源样例：A 前低后高、B 前高后低，交点在 90 秒。"""
    return {
        "probeA": [
            {"time": 0, "temperature": 115.0},
            {"time": 60, "temperature": 115.0},
            {"time": 120, "temperature": 127.0},
            {"time": 180, "temperature": 127.0},
        ],
        "probeB": [
            {"time": 0, "temperature": 127.0},
            {"time": 60, "temperature": 127.0},
            {"time": 120, "temperature": 115.0},
            {"time": 180, "temperature": 115.0},
        ],
    }


def passing_dual_payload() -> dict:
    points = [{"time": t, "temperature": 121.1} for t in (0, 60, 120, 180)]
    return {"probeA": points, "probeB": [dict(p) for p in points]}


def post_dual(payload: dict):
    return client.post("/api/lethality/dual", json=payload)


def errors_of(response) -> list[dict]:
    assert response.status_code == 422, response.text
    return response.json()["detail"]["errors"]


def has_error(errors: list[dict], probe, row, field) -> bool:
    return any(
        e.get("probe") == probe and e["row"] == row and e["field"] == field
        for e in errors
    )


class TestDualHappyPath:
    def test_crossover_response_structure(self):
        response = post_dual(dual_payload())
        assert response.status_code == 200
        body = response.json()
        assert body["threshold"] == pytest.approx(3.0)
        assert body["passed"] is False  # 保守总量约 1.65 min
        assert body["conservativeTotal"] == pytest.approx(1.6476578146, abs=1e-9)
        # 各自总量相等且明显更高：保守结论不能取两份总量的较小值
        assert body["probeATotal"] == pytest.approx(6.2038835124, abs=1e-9)
        assert body["probeBTotal"] == pytest.approx(6.2038835124, abs=1e-9)
        assert body["conservativeTotal"] < min(
            body["probeATotal"], body["probeBTotal"]
        )
        assert body["shortfall"] == pytest.approx(3.0 - 1.6476578146, abs=1e-9)

    def test_crossover_segments_split_at_intersection(self):
        body = post_dual(dual_payload()).json()
        segments = body["segments"]
        assert len(segments) == 4
        assert [s["source"] for s in segments] == ["A", "A", "B", "B"]
        # 交点在 90 秒：第二段结束、第三段开始
        assert segments[1]["endTime"] == pytest.approx(90.0)
        assert segments[2]["startTime"] == pytest.approx(90.0)
        # 段连续覆盖整个区间，贡献之和即保守总量
        assert segments[0]["startTime"] == 0
        assert segments[-1]["endTime"] == 180
        for prev, curr in zip(segments, segments[1:]):
            assert curr["startTime"] == pytest.approx(prev["endTime"])
        assert sum(s["contribution"] for s in segments) == pytest.approx(
            body["conservativeTotal"]
        )

    def test_series_cover_both_probes_for_charting(self):
        body = post_dual(dual_payload()).json()
        assert [p["time"] for p in body["probeA"]["series"]] == [0, 60, 120, 180]
        assert [p["time"] for p in body["probeB"]["series"]] == [0, 60, 120, 180]
        assert body["probeA"]["series"][0]["rate"] == pytest.approx(
            10.0 ** ((115.0 - 121.1) / 10.0)
        )

    def test_identical_probes_pass_and_report_both_source(self):
        body = post_dual(passing_dual_payload()).json()
        assert body["passed"] is True
        assert body["conservativeTotal"] == pytest.approx(3.0)
        assert body["shortfall"] is None
        assert [s["source"] for s in body["segments"]] == ["both"] * 3

    def test_release_decision_uses_unrounded_conservative_total(self):
        # 未舍入保守总量 2.9999999：四舍五入为 3.00 也不放行
        import math

        temperature = 121.1 + 10.0 * math.log10(2.9999999 / 3.0)
        points = [{"time": t, "temperature": temperature} for t in (0, 60, 120, 180)]
        body = post_dual({"probeA": points, "probeB": points}).json()
        assert body["conservativeTotal"] == pytest.approx(2.9999999)
        assert body["passed"] is False
        assert body["shortfall"] == pytest.approx(1e-7, abs=1e-9)


class TestDualValidation:
    def test_probe_a_row_located(self):
        payload = dual_payload()
        payload["probeA"][1]["temperature"] = 99.9
        errors = errors_of(post_dual(payload))
        assert has_error(errors, "A", 2, "temperature")

    def test_probe_b_row_located(self):
        payload = dual_payload()
        payload["probeB"][2]["time"] = 125  # 与前一点（60 秒）间隔 65 秒
        errors = errors_of(post_dual(payload))
        assert has_error(errors, "B", 3, "time")

    def test_mismatched_end_times_rejected_as_whole(self):
        payload = dual_payload()
        payload["probeB"][-1]["time"] = 150
        errors = errors_of(post_dual(payload))
        assert has_error(errors, None, None, "points")

    def test_missing_probe_rejected(self):
        errors = errors_of(post_dual({"probeA": dual_payload()["probeA"]}))
        assert has_error(errors, "B", None, "points")

    def test_interval_rule_applies_to_each_probe(self):
        payload = dual_payload()
        payload["probeA"][1]["time"] = 70  # 与 0 间隔 70 秒
        errors = errors_of(post_dual(payload))
        assert has_error(errors, "A", 2, "time")

    def test_non_object_body_rejected(self):
        response = client.post(
            "/api/lethality/dual",
            content="[1, 2]",
            headers={"Content-Type": "application/json"},
        )
        errors = errors_of(response)
        assert has_error(errors, None, None, "points")

    def test_invalid_json_rejected(self):
        response = client.post(
            "/api/lethality/dual",
            content="{not json",
            headers={"Content-Type": "application/json"},
        )
        errors = errors_of(response)
        assert has_error(errors, None, None, "body")


class TestOriginalEndpointUnchanged:
    """原单探头接口及其响应保持兼容。"""

    def test_single_endpoint_still_works(self):
        response = client.post(
            "/api/lethality",
            json={
                "points": [
                    {"time": t, "temperature": 121.1} for t in (0, 60, 120, 180)
                ]
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["passed"] is True
        assert body["f0"] == pytest.approx(3.0)
        assert set(body) == {"f0", "threshold", "passed", "shortfall", "segments"}

    def test_single_endpoint_error_shape_unchanged(self):
        response = client.post(
            "/api/lethality",
            json={"points": [{"time": 0, "temperature": 99.0}]},
        )
        assert response.status_code == 422
        errors = response.json()["detail"]["errors"]
        # 单探头错误条目不含 probe 字段
        assert all(set(e) == {"row", "field", "message"} for e in errors)
