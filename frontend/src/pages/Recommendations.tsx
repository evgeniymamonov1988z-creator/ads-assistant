import { useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import { ACTION_LABEL, dateTime, money, num, PRIORITY_LABEL, SOURCE_LABEL } from "../lib/format";
import type { AnalysisResponse, MutationChange, Recommendation } from "../lib/types";

interface Props {
  analysis: AnalysisResponse | null;
  loading: boolean;
  onAnalyze: () => void;
  onConfirmed: () => void;
  onSetError: (message: string | null) => void;
  onSetNotice: (message: string | null) => void;
}

const FIELD_LABEL: Record<string, string> = {
  bid: "Ставка",
  daily_budget: "Дневной бюджет",
  minus_words: "Минус-слова",
};

export default function Recommendations({ analysis, loading, onAnalyze, onConfirmed, onSetError, onSetNotice }: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmedBy, setConfirmedBy] = useState(
    () => localStorage.getItem("adassistant_confirmed_by") ?? ""
  );
  const [done, setDone] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState("all");

  const recs = analysis?.recommendations ?? [];
  const visible = useMemo(() => {
    if (filter === "all") return recs;
    if (filter === "actionable") return recs.filter((r) => r.changes.length > 0);
    return recs.filter((r) => r.priority === filter);
  }, [recs, filter]);

  const toggle = (id: string) => setOpen((prev) => ({ ...prev, [id]: !prev[id] }));

  async function confirm(rec: Recommendation) {
    if (confirmedBy.trim().length < 2) {
      onSetError("Укажите, кто подтверждает изменение (имя) — это попадёт в журнал.");
      return;
    }
    localStorage.setItem("adassistant_confirmed_by", confirmedBy.trim());
    setBusy(rec.id);
    onSetError(null);
    onSetNotice(null);
    try {
      const result = await api.confirm(rec.id, confirmedBy.trim());
      setDone((prev) => ({ ...prev, [rec.id]: result.message }));
      onConfirmed();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        onSetError("Предложение устарело (данные обновились). Запустите анализ заново и подтвердите свежее.");
      } else {
        onSetError(err instanceof Error ? err.message : "Не удалось подтвердить изменение.");
      }
    } finally {
      setBusy(null);
    }
  }

  async function reject(rec: Recommendation) {
    setBusy(rec.id);
    onSetError(null);
    try {
      await api.reject(rec.id, confirmedBy.trim() || "пользователь");
      setDone((prev) => ({ ...prev, [rec.id]: "Отклонено, в API ничего не отправлялось." }));
    } catch (err) {
      onSetError(err instanceof Error ? err.message : "Не удалось отклонить предложение.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <div className="field" style={{ minWidth: 260 }}>
          <label htmlFor="confirmedBy">Кто подтверждает</label>
          <input
            id="confirmedBy"
            type="text"
            value={confirmedBy}
            placeholder="Имя, например: Евгений"
            onChange={(e) => setConfirmedBy(e.target.value)}
          />
          <small>Подставляется в журнал рядом со статусом «подтверждено».</small>
        </div>
        <div className="field right" style={{ minWidth: 200 }}>
          <label htmlFor="filter">Показать</label>
          <select
            id="filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{
              width: "100%",
              padding: "9px 11px",
              borderRadius: 8,
              border: "1px solid var(--line)",
              background: "#fbfcff",
              fontFamily: "inherit",
              fontSize: 13.5,
            }}
          >
            <option value="all">Все</option>
            <option value="actionable">Только с изменениями</option>
            <option value="high">Высокий приоритет</option>
            <option value="medium">Средний приоритет</option>
          </select>
        </div>
      </div>

      {!analysis && !loading && (
        <div className="empty">
          Сначала запустите анализ — рекомендации строятся по вашим целям CPA/CTR и дневному бюджету.
          <div style={{ marginTop: 14 }}>
            <button className="btn btn-primary" onClick={onAnalyze}>
              Проанализировать
            </button>
          </div>
        </div>
      )}

      {analysis && visible.length === 0 && (
        <div className="empty">Предложений нет — отклонений от целей не найдено.</div>
      )}

      {visible.map((rec) => (
        <div className="rec" key={rec.id}>
          <div className="rec-head">
            <span className={`pill pill-${rec.priority}`}>{PRIORITY_LABEL[rec.priority]} приоритет</span>
            <span className={`pill pill-${rec.source}`}>{SOURCE_LABEL[rec.source] ?? rec.source}</span>
            <span className="pill pill-proposed">{ACTION_LABEL[rec.action_type]}</span>
            <h3>{rec.title}</h3>
          </div>
          <p className="rec-reason">{rec.reason}</p>

          {rec.metric_snapshot && Object.keys(rec.metric_snapshot).length > 0 && (
            <div className="row small muted" style={{ gap: 14, marginBottom: 10 }}>
              {snapshotLabels(rec.metric_snapshot, analysis?.kpi.currency ?? "RUB").map((text) => (
                <span key={text}>{text}</span>
              ))}
            </div>
          )}

          {rec.changes.length > 0 ? (
            <>
              <button className="preview-toggle" onClick={() => toggle(rec.id)}>
                {open[rec.id] ? "▾ Скрыть превью изменений" : `▸ Превью изменений (${rec.changes.length})`}
              </button>
              {open[rec.id] && <PreviewTable changes={rec.changes} />}
              <div className="rec-foot" style={{ marginTop: 12 }}>
                <button
                  className="btn btn-primary"
                  disabled={busy === rec.id || Boolean(done[rec.id])}
                  onClick={() => confirm(rec)}
                >
                  {busy === rec.id && <span className="spinner" />}
                  {busy === rec.id ? "Отправляю…" : "Подтвердить и применить"}
                </button>
                <button className="btn btn-ghost" disabled={busy === rec.id || Boolean(done[rec.id])} onClick={() => reject(rec)}>
                  Отклонить
                </button>
                <span className="hint">Без подтверждения изменения в API не отправляются.</span>
              </div>
            </>
          ) : (
            <div className="banner banner-info" style={{ marginBottom: 0 }}>
              Это рекомендация без автоматических изменений: сначала проверьте данные в кабинете, потом внесите правки вручную.
            </div>
          )}

          {done[rec.id] && (
            <div className="banner banner-ok" style={{ margin: "12px 0 0" }}>
              {done[rec.id]}
            </div>
          )}
        </div>
      ))}

      {analysis && (
        <p className="small muted" style={{ marginTop: 14 }}>
          Предложения сформированы {dateTime(analysis.generated_at)} по данным за 7 дней и последний день.
        </p>
      )}
    </div>
  );
}

function snapshotLabels(snapshot: Record<string, number | null>, currency: string): string[] {
  const map: Record<string, (value: number) => string> = {
    cost_last_day: (v) => `Расход вчера: ${money(v, currency)}`,
    budget: (v) => `Бюджет: ${money(v, currency)}`,
    overrun: (v) => `Перерасход: ${money(v, currency)}`,
    ctr_7d: (v) => `CTR 7д: ${num(v)}%`,
    target_ctr: (v) => `Цель CTR: ${num(v)}%`,
    clicks_7d: (v) => `Клики 7д: ${Math.round(v)}`,
    cpa_7d: (v) => `CPA 7д: ${money(v, currency)}`,
    target_cpa: (v) => `Цель CPA: ${money(v, currency)}`,
    cost_7d: (v) => `Расход 7д: ${money(v, currency)}`,
  };
  return Object.entries(snapshot)
    .filter(([key, value]) => value !== null && value !== undefined && map[key])
    .map(([key, value]) => map[key](value as number));
}

function PreviewTable({ changes }: { changes: MutationChange[] }) {
  return (
    <div className="preview table-wrap">
      <table>
        <thead>
          <tr>
            <th>Что меняем</th>
            <th>Объект</th>
            <th>Было</th>
            <th>Станет</th>
          </tr>
        </thead>
        <tbody>
          {changes.map((change, index) => (
            <tr key={`${change.entity_id}-${index}`}>
              <td>{FIELD_LABEL[change.field] ?? change.field}</td>
              <td>{change.entity_name}</td>
              <td className="before">{change.before}</td>
              <td className="after">{change.after}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
