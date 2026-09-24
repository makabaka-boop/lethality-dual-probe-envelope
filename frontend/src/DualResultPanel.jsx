import { formatMinutes, formatSeconds, sourceLabel } from './format.js';
import DualChart from './DualChart.jsx';

/**
 * 双探头复核结果：保守结论、两探头各自总量、速率曲线图与保守段明细。
 * 表格与图形使用同一响应的数据。
 */
export default function DualResultPanel({ result }) {
  if (!result) return null;

  const threshold = formatMinutes(result.threshold);
  const conservative = formatMinutes(result.conservativeTotal, 6);

  return (
    <section
      className={`result dual-result ${result.passed ? 'pass' : 'fail'}`}
      aria-label="双探头复核结果"
    >
      <h3>双探头复核结论</h3>
      <p className="conclusion" data-testid="dual-conclusion">
        {result.passed
          ? `放行：保守 F₀ = ${formatMinutes(result.conservativeTotal)} min（未舍入 ${conservative}），达到 ${threshold} min 门槛`
          : `不放行：保守 F₀ = ${formatMinutes(result.conservativeTotal)} min（未舍入 ${conservative}），距 ${threshold} min 门槛尚差 ${formatMinutes(result.shortfall, 6)} min`}
      </p>
      <p className="dual-totals">
        对照（各自独立积分，仅作参考）：探头A 总量{' '}
        <span data-testid="dual-probe-a-total">
          {formatMinutes(result.probeATotal, 6)}
        </span>{' '}
        min，探头B 总量{' '}
        <span data-testid="dual-probe-b-total">
          {formatMinutes(result.probeBTotal, 6)}
        </span>{' '}
        min；放行判定只依据逐时刻取低的保守总量{' '}
        <span data-testid="dual-conservative-total">{conservative}</span> min。
      </p>

      <DualChart
        seriesA={result.probeA.series}
        seriesB={result.probeB.series}
        segments={result.segments}
      />

      <table className="dual-segments">
        <thead>
          <tr>
            <th>段</th>
            <th>时间区间 (s)</th>
            <th>来源探头</th>
            <th>保守速率 起→止</th>
            <th>间隔 (s)</th>
            <th>段贡献 (min)</th>
          </tr>
        </thead>
        <tbody>
          {result.segments.map((s) => (
            <tr key={s.index}>
              <td>{s.index}</td>
              <td>
                {formatSeconds(s.startTime)} → {formatSeconds(s.endTime)}
              </td>
              <td>{sourceLabel(s.source)}</td>
              <td>
                {formatMinutes(s.startRate, 6)} → {formatMinutes(s.endRate, 6)}
              </td>
              <td>{formatSeconds(s.durationSeconds)}</td>
              <td>{formatMinutes(s.contribution, 6)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={5}>保守总量（各段未舍入累加，判定不舍入）</td>
            <td data-testid="dual-conservative-sum">{conservative}</td>
          </tr>
        </tfoot>
      </table>
    </section>
  );
}
