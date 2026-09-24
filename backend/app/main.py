"""FastAPI 入口：蒸汽杀菌致死量 F₀ 复核。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .dual import compute_dual
from .lethality import THRESHOLD_MINUTES, compute_lethality
from .validation import ValidationIssue, validate_dual_payload, validate_payload

app = FastAPI(title="蒸汽杀菌致死量 F₀ 复核", version="1.0.0")

# 内部质检工具：放开跨域以便本地开发直连；生产部署经 nginx 同源代理
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _issue_to_dict(issue: ValidationIssue) -> dict:
    return {"row": issue.row, "field": issue.field, "message": issue.message}


def _validation_response(issues: list[ValidationIssue]) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "message": "采样数据校验失败，整次请求已拒绝",
                "errors": [_issue_to_dict(issue) for issue in issues],
            }
        },
    )


def _dual_issue_to_dict(issue: ValidationIssue) -> dict:
    # 双探头接口的错误条目额外携带探头归属，便于前端定位到对应录入表
    return {**_issue_to_dict(issue), "probe": issue.probe}


def _dual_validation_response(issues: list[ValidationIssue]) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "message": "双探头采样数据校验失败，整次请求已拒绝",
                "errors": [_dual_issue_to_dict(issue) for issue in issues],
            }
        },
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/lethality")
async def calculate(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return _validation_response(
            [ValidationIssue(None, "body", "请求体必须为有效的 JSON")]
        )

    points, issues = validate_payload(payload)
    if issues:
        return _validation_response(issues)

    result = compute_lethality(points)
    return {
        "f0": float(result.f0),
        "threshold": float(THRESHOLD_MINUTES),
        "passed": result.passed,
        "shortfall": None if result.shortfall is None else float(result.shortfall),
        "segments": [
            {
                "index": s.index,
                "startTime": s.start_time,
                "endTime": s.end_time,
                "startTemperature": s.start_temperature,
                "endTemperature": s.end_temperature,
                "startRate": s.start_rate,
                "endRate": s.end_rate,
                "durationSeconds": s.duration_seconds,
                # 段贡献保持未舍入：各段之和须能复算未舍入合计，
                # 仅最终 F₀ 四舍五入到两位小数
                "contribution": s.contribution,
            }
            for s in result.segments
        ],
    }


@app.post("/api/lethality/dual")
async def calculate_dual(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return _dual_validation_response(
            [ValidationIssue(None, "body", "请求体必须为有效的 JSON")]
        )

    points_a, points_b, issues = validate_dual_payload(payload)
    if issues:
        return _dual_validation_response(issues)

    result = compute_dual(points_a, points_b)
    return {
        "threshold": float(THRESHOLD_MINUTES),
        "passed": result.passed,
        # 保守总量与各自总量均为未舍入值：放行判定只用未舍入保守总量
        "conservativeTotal": result.conservative_total,
        "probeATotal": result.probe_a_total,
        "probeBTotal": result.probe_b_total,
        "shortfall": result.shortfall,
        "probeA": {
            "series": [{"time": t, "rate": r} for t, r in result.series_a],
        },
        "probeB": {
            "series": [{"time": t, "rate": r} for t, r in result.series_b],
        },
        "segments": [
            {
                "index": s.index,
                "startTime": s.start_time,
                "endTime": s.end_time,
                "source": s.source,
                "startRate": s.start_rate,
                "endRate": s.end_rate,
                "durationSeconds": s.duration_seconds,
                "contribution": s.contribution,
            }
            for s in result.segments
        ],
    }
