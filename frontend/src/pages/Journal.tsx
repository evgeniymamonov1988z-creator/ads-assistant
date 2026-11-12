import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { ACTION_LABEL, dateTime, SOURCE_LABEL, STATUS_LABEL } from "../lib/format";
import type { JournalEntry } from "../lib/types";

export default function Journal() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEntries(await api.journal());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить журнал.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(
    () => (status === "all" ? entries : entries.filter((entry) => entry.status === status)),
    [entries, status]
  );

  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 14 }}>
        <div className="field" style={{ minWidth: 220 }}>
          <label htmlFor="status">Статус</label>
          <select
            id="status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            style={{
              width: "100%",
              padding: "9px 11px",
              borderRadius: 8,
              border: "1px solid var(--line)",
              background: "#fbfcff",
              fontFamily: "inherit",
            }}
          >
            <option value="all">Все</option>
            <option value="proposed">Предложено</option>
            <option value="confirmed">Подтверждено</option>
            <option value="failed">Ошибка</option>
            <option value="rejected">Отклонено</option>
          </select>
        </div>
        <div className="right row">
          <button className="btn btn-ghost" onClick={load}>
            Обновить
          </button>
          <a className="btn btn-ghost" href={api.journalCsvUrl}>
            Скачать CSV
          </a>
        </div>
      </div>

      {error && <div className="banner banner-error">{error}</div>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Дата</th>
              <th>Кампания</th>
              <th>Источник</th>
              <th>Тип действия</th>
              <th>Статус</th>
              <th>Кто подтвердил</th>
              <th>Что сделано</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((entry) => (
              <tr key={entry.id}>
                <td style={{ whiteSpace: "nowrap" }}>{dateTime(entry.status === "confirmed" ? entry.confirmed_at ?? entry.created_at : entry.created_at)}</td>
                <td>
                  {entry.campaign_name}
                  <div className="small muted">{entry.title}</div>
                </td>
                <td>
                  <span className={`pill pill-${entry.source}`}>{SOURCE_LABEL[entry.source] ?? entry.source}</span>
                </td>
                <td>{ACTION_LABEL[entry.action_type] ?? entry.action_type}</td>
                <td>
                  <span className={`pill pill-${entry.status}`}>{STATUS_LABEL[entry.status] ?? entry.status}</span>
                </td>
                <td>{entry.confirmed_by ?? "—"}</td>
                <td className="small">
                  {entry.result || "—"}
                  {entry.details && <div className="muted">{entry.details}</div>}
                </td>
              </tr>
            ))}
            {!loading && visible.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  Записей пока нет. Журнал заполняется при анализе (статус «предложено») и при подтверждении.
                </td>
              </tr>
            )}
            {loading && (
              <tr>
                <td colSpan={7} className="muted">
                  Загружаю журнал…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
