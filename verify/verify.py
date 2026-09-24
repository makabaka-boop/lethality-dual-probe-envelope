"""一次性验收服务：对运行中的 API 与 Web 做黑盒检查。

全部通过则以退出码 0 结束，否则以 1 结束。仅依赖标准库。
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = os.environ.get("API_URL", "http://api:8000")
WEB_URL = os.environ.get("WEB_URL", "http://web")

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f" — {detail}" if detail and not condition else ""
    print(f"[{status}] {name}{suffix}", flush=True)
    if not condition:
        failures.append(name)


def request(method: str, url: str, payload=None, raw: str | None = None):
    """返回 (status, parsed_body|None|raw_text)。"""
    data = None
    if raw is not None:
        data = raw.encode()
    elif payload is not None:
        data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode()
            try:
                return resp.status, json.loads(text)
            except json.JSONDecodeError:
                return resp.status, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        try:
            return exc.code, json.loads(text)
        except json.JSONDecodeError:
            return exc.code, text


def wait_ready(url: str, name: str, attempts: int = 60) -> bool:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status < 500:
                    print(f"[ OK ] {name} 就绪", flush=True)
                    return True
        except Exception:
            pass
        time.sleep(2)
    print(f"[FAIL] {name} 未就绪: {url}", flush=True)
    return False


def has_error(errors, row, field) -> bool:
    return any(e.get("row") == row and e.get("field") == field for e in errors)


def main() -> int:
    ready = wait_ready(f"{API_URL}/api/health", "API") & wait_ready(f"{WEB_URL}/", "Web")
    if not ready:
        return 1

    passing = {"points": [{"time": t, "temperature": 121.1} for t in (0, 60, 120, 180)]}
    failing = {"points": [{"time": t, "temperature": 121.1} for t in (0, 60, 120, 179)]}

    # 1. 健康检查
    status, body = request("GET", f"{API_URL}/api/health")
    check("API 健康检查", status == 200 and body == {"status": "ok"}, f"{status} {body}")

    # 2. 达标批次：121.1 °C 恒温 180 s → F₀ = 3.00，放行
    status, body = request("POST", f"{API_URL}/api/lethality", passing)
    ok = (
        status == 200
        and body.get("passed") is True
        and abs(body.get("f0", 0) - 3.0) < 1e-9
        and body.get("shortfall") is None
        and len(body.get("segments", [])) == 3
        and all(abs(s.get("contribution", 0) - 1.0) < 1e-9 for s in body["segments"])
    )
    check("达标批次 F₀=3.00 放行且逐段贡献正确", ok, f"{status} {body}")

    # 3. 不足量批次：179 s → F₀ = 2.98，差额 0.02
    status, body = request("POST", f"{API_URL}/api/lethality", failing)
    ok = (
        status == 200
        and body.get("passed") is False
        and abs(body.get("f0", 0) - 2.98) < 1e-9
        and abs(body.get("shortfall", 0) - 0.02) < 1e-9
    )
    check("不足量批次 F₀=2.98 且差额 0.02", ok, f"{status} {body}")

    # 4. 单采样点拒绝
    status, body = request(
        "POST", f"{API_URL}/api/lethality", {"points": [{"time": 0, "temperature": 121.1}]}
    )
    errors = (body or {}).get("detail", {}).get("errors", [])
    check(
        "单采样点返回 422 并指向 points",
        status == 422 and has_error(errors, None, "points"),
        f"{status} {body}",
    )

    # 5. 温度越界定位到行与字段
    bad_temp = {"points": [{"time": 0, "temperature": 121.1}, {"time": 30, "temperature": 99.9}]}
    status, body = request("POST", f"{API_URL}/api/lethality", bad_temp)
    errors = (body or {}).get("detail", {}).get("errors", [])
    check(
        "温度 99.9 °C 返回 422 并定位第 2 行 temperature",
        status == 422 and has_error(errors, 2, "temperature"),
        f"{status} {body}",
    )

    # 6. 间隔超过 60 秒
    bad_gap = {"points": [{"time": 0, "temperature": 121.1}, {"time": 61, "temperature": 121.1}]}
    status, body = request("POST", f"{API_URL}/api/lethality", bad_gap)
    errors = (body or {}).get("detail", {}).get("errors", [])
    check(
        "间隔 61 秒返回 422 并定位第 2 行 time",
        status == 422 and has_error(errors, 2, "time"),
        f"{status} {body}",
    )

    # 7. 非整数秒
    bad_time = {"points": [{"time": 0, "temperature": 121.1}, {"time": 30.5, "temperature": 121.1}]}
    status, body = request("POST", f"{API_URL}/api/lethality", bad_time)
    errors = (body or {}).get("detail", {}).get("errors", [])
    check(
        "非整数秒返回 422 并定位第 2 行 time",
        status == 422 and has_error(errors, 2, "time"),
        f"{status} {body}",
    )

    # 8. 非有限温度（NaN）
    status, body = request(
        "POST",
        f"{API_URL}/api/lethality",
        raw='{"points": [{"time": 0, "temperature": NaN}, {"time": 30, "temperature": 121.1}]}',
    )
    errors = (body or {}).get("detail", {}).get("errors", []) if isinstance(body, dict) else []
    check(
        "NaN 温度返回 422 并定位第 1 行 temperature",
        status == 422 and has_error(errors, 1, "temperature"),
        f"{status} {body}",
    )

    # 9. Web 页面可访问
    status, body = request("GET", f"{WEB_URL}/")
    check(
        "Web 首页返回页面",
        status == 200 and isinstance(body, str) and '<div id="root">' in body,
        f"{status}",
    )

    # 10. 经 Web 同源代理调用 API（nginx → FastAPI 链路）
    status, body = request("POST", f"{WEB_URL}/api/lethality", passing)
    check(
        "经 Web 代理计算 F₀=3.00 放行",
        status == 200 and body.get("passed") is True and abs(body.get("f0", 0) - 3.0) < 1e-9,
        f"{status} {body}",
    )

    print("=" * 48, flush=True)
    if failures:
        print(f"验收失败：{len(failures)} 项未通过", flush=True)
        for name in failures:
            print(f"  - {name}", flush=True)
        return 1
    print("验收通过：全部检查成功", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
