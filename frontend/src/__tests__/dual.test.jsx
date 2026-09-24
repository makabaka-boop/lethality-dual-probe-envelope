import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App.jsx';

// 换源样例：A 前低后高、B 前高后低，速率线在 90 秒相交
const dualCrossoverResponse = {
  threshold: 3.0,
  passed: false,
  conservativeTotal: 1.6476578146716255,
  probeATotal: 6.203883512470167,
  probeBTotal: 6.203883512470167,
  shortfall: 1.3523421853283745,
  probeA: {
    series: [
      { time: 0, rate: 0.24547089170397244 },
      { time: 60, rate: 0.24547089170397244 },
      { time: 120, rate: 3.8904514499428053 },
      { time: 180, rate: 3.8904514499428053 },
    ],
  },
  probeB: {
    series: [
      { time: 0, rate: 3.8904514499428053 },
      { time: 60, rate: 3.8904514499428053 },
      { time: 120, rate: 0.24547089170397244 },
      { time: 180, rate: 0.24547089170397244 },
    ],
  },
  segments: [
    { index: 1, startTime: 0, endTime: 60, source: 'A', startRate: 0.24547089170397244, endRate: 0.24547089170397244, durationSeconds: 60, contribution: 0.24547089170397244 },
    { index: 2, startTime: 60, endTime: 90, source: 'A', startRate: 0.24547089170397244, endRate: 2.067961170823389, durationSeconds: 30, contribution: 0.5783580156318403 },
    { index: 3, startTime: 90, endTime: 120, source: 'B', startRate: 2.067961170823389, endRate: 0.24547089170397244, durationSeconds: 30, contribution: 0.5783580156318403 },
    { index: 4, startTime: 120, endTime: 180, source: 'B', startRate: 0.24547089170397244, endRate: 0.24547089170397244, durationSeconds: 60, contribution: 0.24547089170397244 },
  ],
};

// 重合样例：两探头均为 121.1 °C 恒温 180 秒，保守 F₀ = 3.00 放行
const dualCoincidentResponse = {
  threshold: 3.0,
  passed: true,
  conservativeTotal: 3.0,
  probeATotal: 3.0,
  probeBTotal: 3.0,
  shortfall: null,
  probeA: {
    series: [
      { time: 0, rate: 1 },
      { time: 60, rate: 1 },
      { time: 120, rate: 1 },
      { time: 180, rate: 1 },
    ],
  },
  probeB: {
    series: [
      { time: 0, rate: 1 },
      { time: 60, rate: 1 },
      { time: 120, rate: 1 },
      { time: 180, rate: 1 },
    ],
  },
  segments: [
    { index: 1, startTime: 0, endTime: 60, source: 'both', startRate: 1, endRate: 1, durationSeconds: 60, contribution: 1 },
    { index: 2, startTime: 60, endTime: 120, source: 'both', startRate: 1, endRate: 1, durationSeconds: 60, contribution: 1 },
    { index: 3, startTime: 120, endTime: 180, source: 'both', startRate: 1, endRate: 1, durationSeconds: 60, contribution: 1 },
  ],
};

const singlePassingResponse = {
  f0: 3.0,
  threshold: 3.0,
  passed: true,
  shortfall: null,
  segments: [
    { index: 1, startTime: 0, endTime: 60, startTemperature: 121.1, endTemperature: 121.1, startRate: 1, endRate: 1, durationSeconds: 60, contribution: 1 },
    { index: 2, startTime: 60, endTime: 120, startTemperature: 121.1, endTemperature: 121.1, startRate: 1, endRate: 1, durationSeconds: 60, contribution: 1 },
    { index: 3, startTime: 120, endTime: 180, startTemperature: 121.1, endTemperature: 121.1, startRate: 1, endRate: 1, durationSeconds: 60, contribution: 1 },
  ],
};

function mockFetchResponse(status, body) {
  fetch.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('双探头录入区', () => {
  it('渲染探头A、探头B 两个采样表与复核按钮', () => {
    render(<App />);
    expect(screen.getByLabelText('探头A 第1行 时间')).toHaveValue('0');
    expect(screen.getByLabelText('探头A 第4行 时间')).toHaveValue('180');
    expect(screen.getByLabelText('探头B 第1行 温度')).toHaveValue('121.1');
    expect(
      screen.getByRole('button', { name: '双探头复核计算' }),
    ).toBeInTheDocument();
  });

  it('两个探头表格可独立增删行', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole('button', { name: '探头A 添加行' }));
    expect(screen.getByLabelText('探头A 第5行 时间')).toHaveValue('210');
    // 探头B 行数不受影响
    expect(screen.queryByLabelText('探头B 第5行 时间')).not.toBeInTheDocument();

    await user.click(screen.getByLabelText('探头A 删除第5行'));
    expect(screen.queryByLabelText('探头A 第5行 时间')).not.toBeInTheDocument();
  });
});

describe('双探头复核结果', () => {
  it('重合样例：显示放行、保守总量与“两探头一致”段', async () => {
    const user = userEvent.setup();
    mockFetchResponse(200, dualCoincidentResponse);
    render(<App />);
    await user.click(screen.getByRole('button', { name: '双探头复核计算' }));

    const conclusion = await screen.findByTestId('dual-conclusion');
    expect(conclusion).toHaveTextContent('放行');
    expect(conclusion).toHaveTextContent('3.00');
    expect(screen.getByTestId('dual-conservative-total')).toHaveTextContent(
      '3.000000',
    );
    const rows = within(
      screen.getByLabelText('双探头复核结果'),
    ).getAllByRole('row');
    // 表头 1 行 + 3 段 + 合计 1 行
    expect(rows).toHaveLength(5);
    expect(screen.getAllByText('两探头一致')).toHaveLength(3);
  });

  it('换源样例：交点拆段、来源探头切换、曲线与表格同源', async () => {
    const user = userEvent.setup();
    mockFetchResponse(200, dualCrossoverResponse);
    render(<App />);
    await user.click(screen.getByRole('button', { name: '双探头复核计算' }));

    const conclusion = await screen.findByTestId('dual-conclusion');
    expect(conclusion).toHaveTextContent('不放行');
    expect(screen.getByTestId('dual-conservative-total')).toHaveTextContent(
      '1.647658',
    );
    expect(screen.getByTestId('dual-probe-a-total')).toHaveTextContent(
      '6.203884',
    );

    const result = screen.getByLabelText('双探头复核结果');
    const table = within(result).getByRole('table');
    const segmentRows = within(table).getAllByRole('row');
    // 表头 1 行 + 4 段（交点 90 秒拆段）+ 合计 1 行
    expect(segmentRows).toHaveLength(6);
    expect(segmentRows[2]).toHaveTextContent('60 → 90');
    expect(segmentRows[3]).toHaveTextContent('90 → 120');
    // 来源探头：前两段 A、后两段 B
    const sources = within(table)
      .getAllByText(/^探头[AB]$/)
      .map((cell) => cell.textContent);
    expect(sources).toEqual(['探头A', '探头A', '探头B', '探头B']);

    // 图形与表格使用同一响应：两条探头曲线 + 保守下包络
    expect(screen.getByTestId('curve-probe-a')).toBeInTheDocument();
    expect(screen.getByTestId('curve-probe-b')).toBeInTheDocument();
    expect(screen.getByTestId('curve-envelope')).toBeInTheDocument();
  });

  it('提交体包含 probeA 与 probeB 两组采样点', async () => {
    const user = userEvent.setup();
    mockFetchResponse(200, dualCoincidentResponse);
    render(<App />);
    await user.click(screen.getByRole('button', { name: '双探头复核计算' }));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe('/api/lethality/dual');
    expect(JSON.parse(options.body)).toEqual({
      probeA: [
        { time: 0, temperature: 121.1 },
        { time: 60, temperature: 121.1 },
        { time: 120, temperature: 121.1 },
        { time: 180, temperature: 121.1 },
      ],
      probeB: [
        { time: 0, temperature: 121.1 },
        { time: 60, temperature: 121.1 },
        { time: 120, temperature: 121.1 },
        { time: 180, temperature: 121.1 },
      ],
    });
  });
});

describe('双探头失败只清除本次比较', () => {
  it('双探头 422：显示探头归属错误、清除双探头结果、保留单探头结论', async () => {
    const user = userEvent.setup();
    // 先做一单探头计算，结论保持显示
    mockFetchResponse(200, singlePassingResponse);
    render(<App />);
    await user.click(screen.getByRole('button', { name: '计算致死量' }));
    expect(await screen.findByTestId('conclusion')).toBeInTheDocument();

    // 双探头请求被拒绝
    mockFetchResponse(422, {
      detail: {
        message: '双探头采样数据校验失败，整次请求已拒绝',
        errors: [
          { probe: 'B', row: 2, field: 'temperature', message: '温度须在 100.0 至 140.0 °C 之间' },
        ],
      },
    });
    await user.click(screen.getByRole('button', { name: '双探头复核计算' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('探头B');
    expect(alert).toHaveTextContent('第 2 行');
    // 双探头结果为空，单探头结论不被改写
    expect(screen.queryByTestId('dual-conclusion')).not.toBeInTheDocument();
    expect(screen.getByTestId('conclusion')).toHaveTextContent('放行');
  });

  it('双探头成功后再次失败：只清除本次双探头比较', async () => {
    const user = userEvent.setup();
    mockFetchResponse(200, dualCoincidentResponse);
    render(<App />);
    await user.click(screen.getByRole('button', { name: '双探头复核计算' }));
    expect(await screen.findByTestId('dual-conclusion')).toBeInTheDocument();

    fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await user.click(screen.getByRole('button', { name: '双探头复核计算' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('无法连接服务器');
    expect(screen.queryByTestId('dual-conclusion')).not.toBeInTheDocument();
  });

  it('双探头错误行高亮定位到对应探头表格', async () => {
    const user = userEvent.setup();
    mockFetchResponse(422, {
      detail: {
        message: '双探头采样数据校验失败，整次请求已拒绝',
        errors: [
          { probe: 'A', row: 3, field: 'time', message: '相邻采样间隔不得超过 60 秒' },
        ],
      },
    });
    render(<App />);
    await user.click(screen.getByRole('button', { name: '双探头复核计算' }));

    await screen.findByRole('alert');
    const tableA = screen.getByLabelText('探头A 采样');
    const tableB = screen.getByLabelText('探头B 采样');
    expect(
      within(tableA).getByLabelText('探头A 第3行 时间').closest('tr'),
    ).toHaveClass('row-error');
    const errorRowsInB = within(tableB)
      .queryAllByRole('row')
      .filter((row) => row.classList.contains('row-error'));
    expect(errorRowsInB).toHaveLength(0);
  });
});
