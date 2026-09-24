/** 与后端 /api/lethality 系列接口的真实 HTTP 交互。 */

export class ApiError extends Error {
  constructor(errors) {
    super('采样数据校验失败');
    this.name = 'ApiError';
    this.errors = errors;
  }
}

async function postJson(url, body) {
  let response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError([
      { row: null, field: null, message: '无法连接服务器，请稍后重试' },
    ]);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const errors = data?.detail?.errors ?? [
      { row: null, field: null, message: `服务器返回错误（HTTP ${response.status}）` },
    ];
    throw new ApiError(errors);
  }
  return data;
}

export function calculateLethality(points) {
  return postJson('/api/lethality', { points });
}

/** 双探头复核：两组采样分别提交，后端返回下包络保守积分结果。 */
export function compareDualProbes(probeA, probeB) {
  return postJson('/api/lethality/dual', { probeA, probeB });
}
