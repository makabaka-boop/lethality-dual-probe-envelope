"""采样数据校验。

任一行非法都使整次请求失败；每个问题都带 1-based 行号与字段名，
便于前端定位到具体录入行。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

MIN_POINTS = 2
MAX_INTERVAL_SECONDS = 60
MIN_TEMPERATURE_C = 100.0
MAX_TEMPERATURE_C = 140.0


@dataclass(frozen=True)
class ValidationIssue:
    row: int | None  # 1-based 行号；None 表示请求整体问题
    field: str  # time / temperature / points / body
    message: str


def _validate_time(value: Any, row: int) -> ValidationIssue | None:
    if value is None:
        return ValidationIssue(row, "time", "时间为必填项")
    # bool 是 int 的子类，必须显式排除
    if isinstance(value, bool) or not isinstance(value, int):
        return ValidationIssue(row, "time", "时间必须为整数秒")
    if value < 0:
        return ValidationIssue(row, "time", "时间不得为负数")
    return None


def _validate_temperature(value: Any, row: int) -> ValidationIssue | None:
    if value is None:
        return ValidationIssue(row, "temperature", "温度为必填项")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ValidationIssue(row, "temperature", "温度必须为数字")
    temperature = float(value)
    if not math.isfinite(temperature):
        return ValidationIssue(row, "temperature", "温度必须为有限数")
    if not MIN_TEMPERATURE_C <= temperature <= MAX_TEMPERATURE_C:
        return ValidationIssue(
            row,
            "temperature",
            f"温度须在 {MIN_TEMPERATURE_C:.1f} 至 {MAX_TEMPERATURE_C:.1f} °C 之间",
        )
    return None


def validate_payload(payload: Any) -> tuple[list[tuple[int, float]], list[ValidationIssue]]:
    """返回 (合法采样点列表, 问题列表)；问题非空时调用方必须拒绝请求。"""
    if not isinstance(payload, dict):
        return [], [ValidationIssue(None, "points", "请求体必须为包含 points 数组的对象")]

    raw_points = payload.get("points")
    if not isinstance(raw_points, list):
        return [], [ValidationIssue(None, "points", "points 必须为采样点数组")]

    issues: list[ValidationIssue] = []
    if len(raw_points) < MIN_POINTS:
        issues.append(ValidationIssue(None, "points", f"至少需要 {MIN_POINTS} 个采样点"))

    times: list[int | None] = []
    temperatures: list[float | None] = []
    for i, raw in enumerate(raw_points):
        row = i + 1
        if not isinstance(raw, dict):
            issues.append(ValidationIssue(row, "points", "采样点必须为包含 time 与 temperature 的对象"))
            times.append(None)
            temperatures.append(None)
            continue
        time_issue = _validate_time(raw.get("time"), row)
        temp_issue = _validate_temperature(raw.get("temperature"), row)
        if time_issue:
            issues.append(time_issue)
        if temp_issue:
            issues.append(temp_issue)
        times.append(raw.get("time") if time_issue is None else None)
        temperatures.append(float(raw.get("temperature")) if temp_issue is None else None)

    # 跨行规则仅在相关时间本身合法时检查，避免级联误报
    if times and times[0] is not None and times[0] != 0:
        issues.append(ValidationIssue(1, "time", "首个采样时间必须为 0 秒"))
    for i in range(1, len(times)):
        prev, curr = times[i - 1], times[i]
        if prev is None or curr is None:
            continue
        row = i + 1
        if curr <= prev:
            issues.append(ValidationIssue(row, "time", "时间必须严格递增"))
        elif curr - prev > MAX_INTERVAL_SECONDS:
            issues.append(
                ValidationIssue(row, "time", f"相邻采样间隔不得超过 {MAX_INTERVAL_SECONDS} 秒")
            )

    points = [
        (t, temp)
        for t, temp in zip(times, temperatures)
        if t is not None and temp is not None
    ]
    return points, issues
