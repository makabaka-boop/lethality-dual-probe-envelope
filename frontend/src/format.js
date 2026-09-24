const FIELD_LABELS = {
  time: '时间(秒)',
  temperature: '温度(°C)',
  points: '采样点',
  body: '请求体',
};

export function fieldLabel(field) {
  return FIELD_LABELS[field] ?? field ?? '请求';
}

export function formatMinutes(value, digits = 2) {
  return Number(value).toFixed(digits);
}

/** 秒数展示：整数秒原样显示，交点等非整秒保留至多两位小数。 */
export function formatSeconds(value) {
  return String(Math.round(Number(value) * 100) / 100);
}

const SOURCE_LABELS = {
  A: '探头A',
  B: '探头B',
  both: '两探头一致',
};

export function sourceLabel(source) {
  return SOURCE_LABELS[source] ?? source;
}
