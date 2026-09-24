import { useState } from 'react';
import { ApiError, compareDualProbes } from './api.js';
import { fieldLabel } from './format.js';
import DualResultPanel from './DualResultPanel.jsx';

// 默认示例：两探头均为 121.1 °C 恒温 180 秒（速率线重合，保守 F₀ = 3.00 min）
const DEFAULT_ROWS = [
  { time: '0', temperature: '121.1' },
  { time: '60', temperature: '121.1' },
  { time: '120', temperature: '121.1' },
  { time: '180', temperature: '121.1' },
];

const MIN_ROWS = 2;

function toPayload(rows) {
  // 空值/非数值统一转为 null，交由服务端按行定位报错
  return rows.map((row) => ({
    time: row.time.trim() === '' ? null : Number(row.time),
    temperature: row.temperature.trim() === '' ? null : Number(row.temperature),
  }));
}

function ProbeTable({ probe, rows, errorRows, onUpdate, onAdd, onRemove }) {
  return (
    <table className="samples dual-samples" aria-label={`探头${probe} 采样`}>
      <thead>
        <tr>
          <th>行</th>
          <th>时间 (秒)</th>
          <th>温度 (°C)</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr
            key={index}
            className={errorRows.has(index + 1) ? 'row-error' : undefined}
          >
            <td className="row-index">{index + 1}</td>
            <td>
              <input
                aria-label={`探头${probe} 第${index + 1}行 时间`}
                inputMode="numeric"
                value={row.time}
                onChange={(e) => onUpdate(index, 'time', e.target.value)}
              />
            </td>
            <td>
              <input
                aria-label={`探头${probe} 第${index + 1}行 温度`}
                inputMode="decimal"
                value={row.temperature}
                onChange={(e) => onUpdate(index, 'temperature', e.target.value)}
              />
            </td>
            <td>
              <button
                type="button"
                aria-label={`探头${probe} 删除第${index + 1}行`}
                onClick={() => onRemove(index)}
                disabled={rows.length <= MIN_ROWS}
              >
                删除
              </button>
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td colSpan={4}>
            <button type="button" onClick={onAdd}>
              {`探头${probe} 添加行`}
            </button>
          </td>
        </tr>
      </tfoot>
    </table>
  );
}

function useProbeRows() {
  const [rows, setRows] = useState(DEFAULT_ROWS);

  const updateRow = (index, field, value) => {
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    );
  };

  const addRow = () => {
    setRows((current) => {
      const last = current[current.length - 1];
      const lastTime = last ? Number(last.time) : NaN;
      const canSuggest =
        last && last.time.trim() !== '' && Number.isFinite(lastTime);
      return [
        ...current,
        {
          time: canSuggest ? String(lastTime + 30) : '',
          temperature: last ? last.temperature : '',
        },
      ];
    });
  };

  const removeRow = (index) => {
    setRows((current) => current.filter((_, i) => i !== index));
  };

  return { rows, updateRow, addRow, removeRow };
}

/**
 * 双探头复核入口：两组采样独立录入、独立校验，
 * 结果（含曲线图与保守段明细）只影响本区块，不改写单探头结论。
 */
export default function DualProbeSection() {
  const probeA = useProbeRows();
  const probeB = useProbeRows();
  const [result, setResult] = useState(null);
  const [errors, setErrors] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  const errorRowsFor = (probe) =>
    new Set(
      errors
        .filter((e) => e.probe === probe && e.row != null)
        .map((e) => e.row),
    );

  const submit = async () => {
    setSubmitting(true);
    try {
      const data = await compareDualProbes(
        toPayload(probeA.rows),
        toPayload(probeB.rows),
      );
      setResult(data);
      setErrors([]);
    } catch (err) {
      // 双探头输入或请求失败：只清除本次比较，不影响已显示的单探头结论
      setResult(null);
      setErrors(
        err instanceof ApiError
          ? err.errors
          : [{ row: null, field: null, probe: null, message: '请求失败，请稍后重试' }],
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="dual-section" aria-label="双探头复核">
      <h2>双探头复核</h2>
      <p className="hint">
        两支探头采样时刻可不一致，但均从 0 秒开始且结束于同一秒。系统在两组
        采样时刻的并集上按分段线性致死速率插值，逐时刻取较低速率（速率线
        在区间内部交换高低时在交点拆段）积分下包络，得到保守总量；放行只
        用未舍入的保守总量与 3.00 min 门槛比较。
      </p>

      <div className="dual-tables">
        <ProbeTable
          probe="A"
          rows={probeA.rows}
          errorRows={errorRowsFor('A')}
          onUpdate={probeA.updateRow}
          onAdd={probeA.addRow}
          onRemove={probeA.removeRow}
        />
        <ProbeTable
          probe="B"
          rows={probeB.rows}
          errorRows={errorRowsFor('B')}
          onUpdate={probeB.updateRow}
          onAdd={probeB.addRow}
          onRemove={probeB.removeRow}
        />
      </div>

      <div className="actions">
        <button
          type="button"
          className="primary"
          onClick={submit}
          disabled={submitting}
        >
          {submitting ? '复核中…' : '双探头复核计算'}
        </button>
      </div>

      {errors.length > 0 && (
        <section className="errors" role="alert" aria-label="双探头校验错误">
          <h3>本次双探头复核被拒绝</h3>
          <ul>
            {errors.map((error, i) => (
              <li key={i}>
                {error.probe ? `探头${error.probe} · ` : ''}
                {error.row != null
                  ? `第 ${error.row} 行 · ${fieldLabel(error.field)}`
                  : fieldLabel(error.field)}
                ：{error.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      <DualResultPanel result={result} />
    </section>
  );
}
