import { formatSeconds } from './format.js';

const WIDTH = 640;
const HEIGHT = 260;
const PAD = { left: 56, right: 20, top: 16, bottom: 36 };

function toPolyline(points, x, y) {
  return points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.time).toFixed(2)},${y(p.rate).toFixed(2)}`)
    .join(' ');
}

/**
 * 双探头致死速率曲线图：两条探头速率折线与保守下包络。
 * 数据全部来自复核接口的同一响应（series 画探头曲线，segments 画下包络）。
 */
export default function DualChart({ seriesA, seriesB, segments }) {
  const envelope = [
    ...segments.map((s) => ({ time: s.startTime, rate: s.startRate })),
    {
      time: segments[segments.length - 1].endTime,
      rate: segments[segments.length - 1].endRate,
    },
  ];

  const allRates = [...seriesA, ...seriesB, ...envelope].map((p) => p.rate);
  const xMax = Math.max(...seriesA.map((p) => p.time), ...seriesB.map((p) => p.time));
  const yMax = Math.max(...allRates) * 1.08 || 1;

  const x = (t) => PAD.left + (t / xMax) * (WIDTH - PAD.left - PAD.right);
  const y = (r) => PAD.top + (1 - r / yMax) * (HEIGHT - PAD.top - PAD.bottom);

  const xTicks = [0, xMax / 2, xMax];
  const yTicks = [0, yMax / 2, yMax];

  return (
    <figure className="dual-chart" aria-label="探头致死速率曲线与保守下包络">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img">
        <title>探头致死速率曲线与保守下包络</title>
        {/* 坐标轴 */}
        <line
          x1={PAD.left}
          y1={HEIGHT - PAD.bottom}
          x2={WIDTH - PAD.right}
          y2={HEIGHT - PAD.bottom}
          stroke="#9fb3c8"
        />
        <line
          x1={PAD.left}
          y1={PAD.top}
          x2={PAD.left}
          y2={HEIGHT - PAD.bottom}
          stroke="#9fb3c8"
        />
        {xTicks.map((t) => (
          <text
            key={`x-${t}`}
            x={x(t)}
            y={HEIGHT - PAD.bottom + 18}
            textAnchor="middle"
            className="tick"
          >
            {formatSeconds(t)}s
          </text>
        ))}
        {yTicks.map((r) => (
          <text
            key={`y-${r}`}
            x={PAD.left - 6}
            y={y(r) + 4}
            textAnchor="end"
            className="tick"
          >
            {r.toFixed(2)}
          </text>
        ))}
        {/* 两条探头速率曲线 */}
        <path
          data-testid="curve-probe-a"
          d={toPolyline(seriesA, x, y)}
          fill="none"
          stroke="#0b6bcb"
          strokeWidth="2"
        />
        <path
          data-testid="curve-probe-b"
          d={toPolyline(seriesB, x, y)}
          fill="none"
          stroke="#d97706"
          strokeWidth="2"
        />
        {/* 保守下包络（按段拆分后的逐时刻较低速率） */}
        <path
          data-testid="curve-envelope"
          d={toPolyline(envelope, x, y)}
          fill="none"
          stroke="#1c7c3c"
          strokeWidth="3.5"
          strokeLinejoin="round"
        />
      </svg>
      <figcaption className="legend">
        <span className="legend-item probe-a">探头A</span>
        <span className="legend-item probe-b">探头B</span>
        <span className="legend-item envelope">保守下包络</span>
      </figcaption>
    </figure>
  );
}
