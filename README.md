# 蒸汽杀菌致死量 F₀ 复核

常温乳品批次完成蒸汽杀菌后，质检员在此录入釜内探头的时间—温度采样，系统按梯形法积分复核致死量 F₀，达到 **3.00 min** 即放行。

## 业务规则

- 每个采样点的致死速率：`rate = 10^((T - 121.1) / 10)`（T 为 °C）。
- 相邻两点按梯形法积分：`段贡献 = (rate₁ + rate₂) / 2 × Δt秒 / 60`（分钟）。
- 各段以**未舍入**的值累加，最终 F₀ **四舍五入保留两位小数**；≥ 3.00 min 判定放行。
- 采样约束：至少 2 个点；时间从 0 秒起的整数秒且严格递增；相邻间隔 ≤ 60 秒；温度为 100.0–140.0 °C 的有限数。
- 任一行非法 → 整次请求失败（HTTP 422），响应指明行号与字段，前端同时清除旧结论。
- 不足量批次显示距门槛的差额；达标批次展示逐段贡献，可逐段复算放行值。

## 快速开始（Docker Compose）

```bash
docker compose up --build -d        # 启动 api + web
docker compose run --rm verify      # 一次性验收服务：黑盒检查全部通过则退出码为 0
```

浏览器打开 <http://localhost:8080>。Web 宿主端口可用环境变量覆盖：

```bash
WEB_PORT=9000 docker compose up --build -d   # 改为 http://localhost:9000
```

架构：`web`（nginx，伺服 React 构建产物并把 `/api` 同源代理到 `api`）→ `api`（FastAPI，致死量积分与校验）→ `verify`（一次性验收容器，跑完即退出）。

## 故障排查

- **web 一直不健康、verify 与首页无法启动**：旧版 `frontend/nginx.conf` 在 `proxy_pass` 中使用字面主机名，nginx 只在启动时解析一次 `api`；若此刻 `api` 尚未注册到 Docker 网络 DNS（启动顺序、容器重启、旧版 compose 忽略健康条件），nginx 会以 `host not found in upstream` 退出，web 容器随之不健康，依赖它的 verify 也被连锁阻塞。当前配置已改为 `resolver 127.0.0.11` + 变量式 `proxy_pass`，在请求时解析上游：nginx 不再因 `api` 未就绪而退出，`api` 恢复后 `/api` 自动可用，静态首页始终可访问。
- 查看健康检查失败原因：`docker compose ps` 后 `docker inspect --format '{{json .State.Health}}' <容器>`。
- 手动复跑验收：`docker compose run --rm verify`（verify 自身会等待服务就绪，最长 120 秒）。

## 测试

| 层 | 工具 | 运行 |
| --- | --- | --- |
| 计算边界 | pytest | `cd backend && pip install -r requirements-dev.txt && python -m pytest` |
| 录入交互 | Vitest | `cd frontend && npm ci && npm test` |
| 前后端联调 | Playwright | `docker compose up -d --build && cd frontend && npx playwright install chromium && npm run e2e` |

Playwright 也可整体容器化运行（无需本机装浏览器）：

```bash
docker compose --profile e2e run --rm e2e
```

联调测试默认打向 `http://localhost:8080`，可用 `BASE_URL` 或 `WEB_PORT` 环境变量覆盖。所有测试均走真实 HTTP 与真实计算，无固定结果或假接口。

## API

### `POST /api/lethality`

请求：

```json
{
  "points": [
    { "time": 0,   "temperature": 121.1 },
    { "time": 60,  "temperature": 121.1 },
    { "time": 120, "temperature": 121.1 },
    { "time": 180, "temperature": 121.1 }
  ]
}
```

达标响应（200）：

```json
{
  "f0": 3.0,
  "threshold": 3.0,
  "passed": true,
  "shortfall": null,
  "segments": [
    {
      "index": 1,
      "startTime": 0,
      "endTime": 60,
      "startTemperature": 121.1,
      "endTemperature": 121.1,
      "startRate": 1.0,
      "endRate": 1.0,
      "durationSeconds": 60,
      "contribution": 1.0
    }
  ]
}
```

校验失败响应（422，`row` 为 1-based 行号，`null` 表示整体问题）：

```json
{
  "detail": {
    "message": "采样数据校验失败，整次请求已拒绝",
    "errors": [
      { "row": 2, "field": "temperature", "message": "温度须在 100.0 至 140.0 °C 之间" }
    ]
  }
}
```

### `GET /api/health`

返回 `{"status": "ok"}`。

## 本地开发

```bash
cd backend && pip install -r requirements-dev.txt
uvicorn app.main:app --reload          # http://localhost:8000

cd frontend && npm ci && npm run dev   # http://localhost:5173（/api 已代理到 8000）
```
