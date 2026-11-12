import type { AnalysisResponse, HealthResponse } from "../lib/types";
import { dateTime, int, money, num, SOURCE_LABEL } from "../lib/format";

interface Props {
  analysis: AnalysisResponse | null;
  loading: boolean;
  onAnalyze: () => void;
  health: HealthResponse | null;
  onOpenRecommendations: () => void;
}

export default function Dashboard({ analysis, loading, onAnalyze, health, onOpenRecommendations }: Props) {
  if (loading && !analysis) {
    return (
      <div className="card">
        <div className="empty">Собираю статистику из рекламных кабинетов…</div>
      </div>
    );
  }
  if (!analysis) {
    return (
      <div className="card">
        <div className="empty">
          Пока нет данных. Нажмите «Проанализировать» — система возьмёт 7 дней и последний день и сравнит с вашими целями.
        </div>
        {health && (
          <div className="row" style={{ justifyContent: "center", gap: 8 }}>
            {health.sources.map((s) => (
              <span key={s.source} className={`pill ${s.ok ? "pill-confirmed" : "pill-high"}`}>
                {s.ok ? "✓" : "!"} {s.message}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  const { summary, kpi, campaigns, recommendations, anomalies } = analysis;
  const cur = kpi.currency;
  const clicks7 = summary.clicks;
  const payload = recommendations.filter((r) => r.changes.length > 0);
  const cpaOk = summary.cpa !== null && summary.cpa <= kpi.target_cpa;
  const ctrOk = summary.ctr >= kpi.target_ctr;

  return (
    <>
      <div className="grid-metrics">
        <div className="metric">
          <div className="label">Расход за 7 дней</div>
          <div className="value">{money(summary.cost, cur)}</div>
          <div className="sub">В среднем {money(summary.cost_per_day, cur)} в день</div>
        </div>
        <div className="metric">
          <div className="label">Клики / показы</div>
          <div className="value">{int(clicks7)}</div>
          <div className="sub">Показов: {int(summary.impressions)}</div>
        </div>
        <div className="metric">
          <div className="label">CTR (цель {num(kpi.target_ctr)}%)</div>
          <div className="value">{num(summary.ctr)}%</div>
          <div className="sub">
            <span className={ctrOk ? "delta-good" : "delta-bad"}>
              {ctrOk ? "в норме" : "ниже цели"}
            </span>{" "}
            · стоимость клика {money(summary.cpc, cur)}
          </div>
        </div>
        <div className="metric">
          <div className="label">CPA (цель {money(kpi.target_cpa, cur)})</div>
          <div className="value">{money(summary.cpa, cur)}</div>
          <div className="sub">
            Конверсий: {num(summary.conversions, 1)} ·{" "}
            <span className={cpaOk ? "delta-good" : "delta-bad"}>{cpaOk ? "в норме" : "дороже цели"}</span>
          </div>
        </div>
        <div className="metric">
          <div className="label">Предложений к внесению</div>
          <div className="value">{payload.length}</div>
          <div className="sub">
            <button className="preview-toggle" onClick={onOpenRecommendations}>
              Посмотреть и подтвердить →
            </button>
          </div>
        </div>
      </div>

      {payload.length > 0 && (
        <div className="banner banner-info" style={{ marginTop: 16 }}>
          Есть {payload.length} предложение(й). Ни одно изменение ещё не отправлено в API — откройте «Рекомендации»
          и подтвердите нужные.
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Кампании: 7 дней и последний день</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Кампания</th>
                <th>Источник</th>
                <th className="num">Показы</th>
                <th className="num">Клики</th>
                <th className="num">CTR</th>
                <th className="num">Расход</th>
                <th className="num">CPA</th>
                <th className="num">Бюджет/день</th>
                <th className="num">Расход вчера</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((item) => {
                const c = item.campaign;
                const cpaBad = c.cpa !== null && c.cpa > kpi.target_cpa;
                const ctrBad = c.ctr > 0 && c.ctr < kpi.target_ctr;
                const overrun = c.daily_budget !== null && item.lastDay.cost > c.daily_budget;
                return (
                  <tr key={`${c.source}-${c.id}`}>
                    <td>{c.name}</td>
                    <td>
                      <span className={`pill pill-${c.source}`}>{SOURCE_LABEL[c.source] ?? c.source}</span>
                    </td>
                    <td className="num">{int(c.impressions)}</td>
                    <td className="num">{int(c.clicks)}</td>
                    <td className="num">{ctrBad ? <span className="delta-bad">{num(c.ctr)}%</span> : `${num(c.ctr)}%`}</td>
                    <td className="num">{money(c.cost, cur)}</td>
                    <td className="num">{cpaBad ? <span className="delta-bad">{money(c.cpa, cur)}</span> : money(c.cpa, cur)}</td>
                    <td className="num">{c.daily_budget !== null ? money(c.daily_budget, cur) : "не задан"}</td>
                    <td className="num">
                      {overrun ? <span className="delta-bad">{money(item.lastDay.cost, cur)}</span> : money(item.lastDay.cost, cur)}
                    </td>
                  </tr>
                );
              })}
              {campaigns.length === 0 && (
                <tr>
                  <td colSpan={9} className="muted">
                    Кампаний нет — проверьте подключение кабинетов.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 10 }}>
          Красным отмечено: CTR/CPA хуже цели, расход вчера выше дневного бюджета. Данные собраны {dateTime(analysis.generated_at)}.
        </p>
      </div>

      <div className="card">
        <h2>Аномалии</h2>
        {anomalies.length === 0 ? (
          <div className="muted small">Отклонений от целей не обнаружено.</div>
        ) : (
          <ul className="anomalies">
            {anomalies.map((text, index) => (
              <li key={index}>{text}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="card">
        <h2>Проверка подключений</h2>
        <div className="row">
          {(health?.sources ?? []).map((s) => (
            <span key={s.source} className={`pill ${s.ok ? "pill-confirmed" : "pill-high"}`}>
              {s.ok ? "✓" : "!"} {s.message}
            </span>
          ))}
          {!health && <span className="muted small">Проверяю…</span>}
        </div>
        <div style={{ marginTop: 12 }}>
          <button className="btn btn-ghost" onClick={onAnalyze}>
            Обновить анализ
          </button>
        </div>
      </div>
    </>
  );
}
