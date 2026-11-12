import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { int as fmtInt, num as fmtNum } from "../lib/format";
import type { MetrikaData, ServerLogData } from "../lib/types";

const DAY_OPTIONS = [7, 14, 30];

export default function Site() {
  const [days, setDays] = useState(7);
  const [metrika, setMetrika] = useState<MetrikaData | null>(null);
  const [log, setLog] = useState<ServerLogData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (period: number) => {
    setLoading(true);
    const [m, l] = await Promise.allSettled([api.metrika(period), api.serverlog(period)]);
    setMetrika(m.status === "fulfilled" ? m.value : { ok: false, message: "Не удалось получить данные Метрики." } as MetrikaData);
    setLog(l.status === "fulfilled" ? l.value : { ok: false, message: "Не удалось прочитать журнал.", events: [] } as ServerLogData);
    setLoading(false);
  }, []);

  useEffect(() => {
    load(days);
  }, [days, load]);

  const maxDay = Math.max(1, ...(metrika?.by_day ?? []).map((d) => d.visits));
  const maxHour = Math.max(1, ...(log?.by_hour ?? []).map((h) => h.count));

  return (
    <div className="stack">
      <div className="row space-between">
        <div className="seg">
          {DAY_OPTIONS.map((d) => (
            <button key={d} className={days === d ? "active" : ""} onClick={() => setDays(d)}>
              {d} дней
            </button>
          ))}
        </div>
        <button className="btn btn-ghost" onClick={() => load(days)} disabled={loading}>
          {loading && <span className="spinner" />}
          Обновить
        </button>
      </div>

      <div className="card">
        <h2>Яндекс Метрика</h2>
        {!metrika && <div className="empty">Загружаю…</div>}
        {metrika && !metrika.ok && <div className="banner banner-warn">{metrika.message}</div>}
        {metrika?.ok && (
          <>
            <div className="kpi-grid">
              <div className="kpi">
                <span>Визиты</span>
                <strong>{fmtInt(metrika.visits)}</strong>
              </div>
              <div className="kpi">
                <span>Посетители</span>
                <strong>{fmtInt(metrika.users)}</strong>
              </div>
              <div className="kpi">
                <span>Просмотры</span>
                <strong>{fmtInt(metrika.pageviews)}</strong>
              </div>
              <div className="kpi">
                <span>Отказы</span>
                <strong>{fmtNum(metrika.bounce_rate, 1)}%</strong>
              </div>
              <div className="kpi">
                <span>Скачивания демо (цели)</span>
                <strong>{metrika.downloads ?? 0}</strong>
              </div>
            </div>
            <p className="muted small">
              Период: {metrika.date_from} — {metrika.date_to}. Сайт считает визиты, а не показы рекламы.
            </p>

            <h3 className="sec">Визиты по дням</h3>
            <div className="bars">
              {(metrika.by_day ?? []).map((d) => (
                <div className="bar-col" key={d.date} title={`${d.date}: ${d.visits} визитов`}>
                  <div className="bar" style={{ height: `${Math.max(3, (d.visits / maxDay) * 100)}%` }} />
                  <span>{d.date.slice(8)}</span>
                </div>
              ))}
              {!metrika.by_day?.length && <div className="empty">За период визитов нет.</div>}
            </div>

            <div className="two-col">
              <div>
                <h3 className="sec">Цели</h3>
                {(metrika.goals ?? []).length === 0 && <div className="muted small">Цели не достигнуты за период.</div>}
                <table className="table">
                  <tbody>
                    {(metrika.goals ?? []).map((g) => (
                      <tr key={g.goal_id || g.name}>
                        <td>{g.name}</td>
                        <td className="num">{g.reaches}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <h3 className="sec">Откуда пришли</h3>
                <table className="table">
                  <tbody>
                    {(metrika.sources ?? []).map((s) => (
                      <tr key={s.source}>
                        <td>{s.source}</td>
                        <td className="num">{fmtInt(s.visits)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="card">
        <div className="row space-between">
          <h2>Запуски и скачивания из журнала сервера</h2>
          {log?.ok && (
            <a className="btn btn-ghost" href={`/api/serverlog.csv?days=${days}`}>
              Выгрузить CSV
            </a>
          )}
        </div>
        {!log && <div className="empty">Загружаю…</div>}
        {log && !log.ok && <div className="banner banner-warn">{log.message}</div>}
        {log?.ok && (
          <>
            <div className="kpi-grid">
              <div className="kpi">
                <span>Всего скачиваний</span>
                <strong>{log.summary?.total ?? 0}</strong>
              </div>
              <div className="kpi">
                <span>Сегодня</span>
                <strong>{log.summary?.today ?? 0}</strong>
              </div>
              <div className="kpi">
                <span>Вчера</span>
                <strong>{log.summary?.yesterday ?? 0}</strong>
              </div>
              <div className="kpi">
                <span>Уникальных адресов</span>
                <strong>{log.summary?.unique_ips ?? 0}</strong>
              </div>
              <div className="kpi">
                <span>Неудачных обращений</span>
                <strong>{log.summary?.errors ?? 0}</strong>
              </div>
            </div>

            <h3 className="sec">Когда скачивают (по часам)</h3>
            <div className="bars small-bars">
              {(log.by_hour ?? []).map((h) => (
                <div className="bar-col" key={h.hour} title={`${h.hour}:00 — ${h.count} скачиваний`}>
                  <div className="bar" style={{ height: `${Math.max(2, (h.count / maxHour) * 100)}%` }} />
                  <span>{Number(h.hour) % 3 === 0 ? h.hour : ""}</span>
                </div>
              ))}
            </div>

            <h3 className="sec">Что скачивают чаще</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>Файл</th>
                  <th className="num">Раз</th>
                </tr>
              </thead>
              <tbody>
                {(log.top_files ?? []).map((f) => (
                  <tr key={f.file}>
                    <td className="mono">{f.file}</td>
                    <td className="num">{f.count}</td>
                  </tr>
                ))}
                {!log.top_files?.length && (
                  <tr>
                    <td colSpan={2} className="muted">
                      За период скачиваний в журнале не найдено.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>

            <h3 className="sec">Последние запуски</h3>
            <table className="table">
              <thead>
                <tr>
                  <th>Когда</th>
                  <th>Файл</th>
                  <th>Откуда (IP)</th>
                  <th className="num">Размер, КБ</th>
                </tr>
              </thead>
              <tbody>
                {(log.events ?? []).slice(0, 50).map((e, i) => (
                  <tr key={`${e.at}-${i}`}>
                    <td>{e.at}</td>
                    <td className="mono">{e.file}</td>
                    <td className="mono">{e.ip}</td>
                    <td className="num">{e.size_kb || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <small className="muted">
              Показываем не больше 50 последних записей. Роботов и поисковые системы отфильтровываем, чтобы не завышать
              цифры.
            </small>
          </>
        )}
      </div>
    </div>
  );
}
