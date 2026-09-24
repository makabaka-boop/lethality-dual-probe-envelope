/** 与后端 /api/lethality 的真实 HTTP 交互。 */

export class ApiError extends Error {
  constructor(errors) {
    super('采样数据校验失败');
    this.name = 'ApiError';
    this.errors = errors;
  }
}

export async function calculateLethality(points) {
  let response;
  try {
    response = await fetch('/api/lethality', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ points }),
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
