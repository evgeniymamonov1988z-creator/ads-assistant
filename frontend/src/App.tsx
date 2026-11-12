import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, getApiKey, setApiKey } from "./lib/api";
import { SOURCE_LABEL } from "./lib/format";
import type { AnalysisResponse, HealthResponse, KpiSettings } from "./lib/types";
import Dashboard from "./pages/Dashboard";
import Recommendations from "./pages/Recommendations";
import Settings from "./pages/Settings";
import Journal from "./pages/Journal";
import Credentials from "./pages/Credentials";
import Site from "./pages/Site";

export type Tab = "dashboard" | "recommendations" | "settings" | "journal" | "site" | "credentials";

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [kpi, setKpi] = useState<KpiSettings | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [apiKeyDraft, setApiKeyDraft] = useState(getApiKey());
  const [needsKey, setNeedsKey] = useState(false);

  useEffect(() => {
    api.settings().then(setKpi).catch(() => undefined);
    api.health().then(setHealth).catch(() => undefined);
  }, []);

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const result = await api.analyze();
      setAnalysis(result);
      setKpi(result.kpi);
      const count = result.recommendations.filter((r) => r.changes.length > 0).length;
      setNotice(
        count > 0
          ? `Готово: найдено рекомендаций с изменениями — ${count}. Ничего не отправлено без вашего подтверждения.`
          : "Готово: критичных отклонений нет, изменений не предлагаем."
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setNeedsKey(true);
      setError(err instanceof Error ? err.message : "Не удалось выполнить анализ.");
    } finally {
      setLoading(false);
    }
  }, []);

  const pendingCount = useMemo(
    () => analysis?.recommendations.filter((r) => r.changes.length > 0).length ?? 0,
    [analysis]
  );

  const sourcesConfigured = Object.entries(health?.sources ?? {}).filter(([, s]) => s.ok).length;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">
          Рекламный ассистент
          <span>Яндекс Директ · Google Ads</span>
        </div>
        <nav className="nav">
          <button className={tab === "dashboard" ? "active" : ""} onClick={() => setTab("dashboard")}>
            Дашборд
          </button>
          <button className={tab === "recommendations" ? "active" : ""} onClick={() => setTab("recommendations")}>
            Рекомендации {pendingCount > 0 && <span className="badge">{pendingCount}</span>}
          </button>
          <button className={tab === "site" ? "active" : ""} onClick={() => setTab("site")}>
            Метрика и запуски
          </button>
          <button className={tab === "journal" ? "active" : ""} onClick={() => setTab("journal")}>
            Журнал
          </button>
          <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
            Настройки KPI
          </button>
          <button className={tab === "credentials" ? "active" : ""} onClick={() => setTab("credentials")}>
            Токены
          </button>
        </nav>
        <div className="sidebar-footer">
          {health ? (
            <>
              {health.mock_mode ? "Демо-режим: реальные API не вызываются" : `Подключено источников: ${sourcesConfigured}`}
              <br />
              Изменения уходят в рекламные кабинеты только после подтверждения.
            </>
          ) : (
            "Проверяю подключение…"
          )}
        </div>
      </aside>

      <main className="main">
        <div className="page-head">
          <div>
            <h1>
              {tab === "dashboard" && "Сводка по рекламе"}
              {tab === "recommendations" && "Рекомендации"}
              {tab === "journal" && "Журнал действий"}
              {tab === "settings" && "Целевые KPI"}
              {tab === "site" && "Сайт: Метрика и запуски"}
              {tab === "credentials" && "Токены и подключение"}
            </h1>
            <p>
              {tab === "site" && "Визиты и скачивания с сайта · данные Яндекс Метрики и журнала сервера"}
              {tab === "credentials"
                ? "Вставьте токены рекламных сервисов — они хранятся только на этом компьютере"
                : "Статистика за 7 дней и за последний день · CPA, CTR, расход · сравнение с вашими целями"}
            </p>
          </div>
          {tab !== "credentials" && tab !== "site" && (
            <button className="btn btn-primary" onClick={runAnalysis} disabled={loading}>
              {loading && <span className="spinner" />}
              {loading ? "Анализирую…" : "Проанализировать"}
            </button>
          )}
        </div>

        {needsKey && (
          <div className="banner banner-warn">
            Сервер требует ключ доступа к API. Введите ключ из переменной API_KEY на сервере.
            <div className="row" style={{ marginTop: 10 }}>
              <input
                type="text"
                style={{ maxWidth: 320 }}
                value={apiKeyDraft}
                onChange={(e) => setApiKeyDraft(e.target.value)}
                placeholder="Ключ доступа"
              />
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setApiKey(apiKeyDraft);
                  setNeedsKey(false);
                  setError(null);
                }}
              >
                Сохранить
              </button>
            </div>
          </div>
        )}

        {error && <div className="banner banner-error">{error}</div>}
        {notice && !error && <div className="banner banner-ok">{notice}</div>}

        {analysis?.warnings?.length ? (
          <div className="banner banner-warn">
            <strong>Что стоит знать:</strong>
            <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
              {analysis.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {tab === "dashboard" && (
          <Dashboard analysis={analysis} loading={loading} onAnalyze={runAnalysis} health={health} onOpenRecommendations={() => setTab("recommendations")} />
        )}
        {tab === "recommendations" && (
          <Recommendations
            analysis={analysis}
            loading={loading}
            onAnalyze={runAnalysis}
            onConfirmed={() => {
              setNotice("Изменения отправлены в рекламный кабинет и записаны в журнал.");
            }}
            onSetError={setError}
            onSetNotice={setNotice}
          />
        )}
        {tab === "settings" && kpi && <Settings kpi={kpi} onSaved={setKpi} />}
        {tab === "journal" && <Journal />}
        {tab === "site" && <Site />}
        {tab === "credentials" && <Credentials />}

        {Object.keys(SOURCE_LABEL).length > 0 && tab === "dashboard" && !analysis && !loading && (
          <div className="card">
            <div className="empty">
              Нажмите «Проанализировать», чтобы собрать статистику и получить предложения по кампаниям.
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
