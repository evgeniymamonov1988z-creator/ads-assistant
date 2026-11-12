import { useState } from "react";
import { api } from "../lib/api";
import type { KpiSettings } from "../lib/types";

interface Props {
  kpi: KpiSettings;
  onSaved: (kpi: KpiSettings) => void;
}

const NUMERIC_FIELDS: Array<{ key: keyof KpiSettings; label: string; hint: string; step?: string }> = [
  { key: "target_cpa", label: "Целевой CPA", hint: "Сколько готовы платить за одну конверсию (скачивание демо).", step: "0.01" },
  { key: "target_ctr", label: "Целевой CTR, %", hint: "Ниже этого значения система предложит чистку запросов и улучшение объявлений.", step: "0.01" },
  { key: "daily_budget", label: "Дневной бюджет", hint: "Опорный бюджет на кампанию в сутки; используется как верхняя граница предложений.", step: "0.01" },
  { key: "overrun_tolerance_pct", label: "Допуск перерасхода, %", hint: "На сколько расход может превысить бюджет, прежде чем это станет аномалией.", step: "1" },
  { key: "ctr_deficit_tolerance_pct", label: "Допуск по CTR, %", hint: "Насколько CTR может быть ниже цели, прежде чем сработает правило.", step: "1" },
  { key: "cpa_overrun_tolerance_pct", label: "Допуск превышения CPA, %", hint: "Насколько CPA может быть выше цели без рекомендации.", step: "1" },
  { key: "bid_step_pct", label: "Шаг снижения ставок, %", hint: "На сколько процентов снижаем ставки в предложении по CPA.", step: "1" },
  { key: "min_clicks_for_judgement", label: "Мин. кликов для вывода", hint: "При меньшем числе кликов статистика считается нерепрезентативной.", step: "1" },
];

export default function Settings({ kpi, onSaved }: Props) {
  const [form, setForm] = useState<KpiSettings>(kpi);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function update(key: keyof KpiSettings, raw: string) {
    const value = Number(raw.replace(",", "."));
    setForm((prev) => ({ ...prev, [key]: Number.isFinite(value) ? value : 0 }));
  }

  async function save() {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await api.saveSettings(form);
      onSaved(saved);
      setMessage("Цели сохранены. Следующий анализ будет считать по ним.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить настройки.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h2>Целевые значения</h2>
      {message && <div className="banner banner-ok">{message}</div>}
      {error && <div className="banner banner-error">{error}</div>}
      <div className="form-grid">
        {NUMERIC_FIELDS.map((field) => (
          <div className="field" key={field.key}>
            <label htmlFor={String(field.key)}>{field.label}</label>
            <input
              id={String(field.key)}
              type="number"
              step={field.step ?? "1"}
              min={0}
              value={String(form[field.key] ?? 0)}
              onChange={(e) => update(field.key, e.target.value)}
            />
            <small>{field.hint}</small>
          </div>
        ))}
      </div>
      <div className="row" style={{ marginTop: 18 }}>
        <button className="btn btn-primary" onClick={save} disabled={saving}>
          {saving && <span className="spinner" />}
          {saving ? "Сохраняю…" : "Сохранить цели"}
        </button>
        <span className="muted small">
          Настройки хранятся на сервере и применяются при каждом анализе.
        </span>
      </div>
    </div>
  );
}
