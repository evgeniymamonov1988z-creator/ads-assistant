import { useEffect, useState } from "react";
import { api, ApiError, setApiKey, getApiKey } from "../lib/api";
import type { CredentialsView, CredentialSource } from "../lib/types";

export default function Credentials() {
  const [view, setView] = useState<CredentialsView | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [clears, setClears] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tests, setTests] = useState<Record<string, { ok: boolean; message: string }> | null>(null);
  const [keyDraft, setKeyDraft] = useState(getApiKey());
  const [needKey, setNeedKey] = useState(false);

  useEffect(() => {
    api
      .credentials()
      .then(setView)
      .catch((err) => setError(err instanceof Error ? err.message : "Не удалось загрузить токены."));
  }, []);

  function handleError(err: unknown) {
    if (err instanceof ApiError && err.status === 401) setNeedKey(true);
    setError(err instanceof Error ? err.message : "Не удалось сохранить.");
  }

  async function save(source: CredentialSource) {
    setSaving(source.source);
    setError(null);
    setMessage(null);
    try {
      const values: Record<string, string> = {};
      for (const field of source.fields) {
        const draft = drafts[field.key];
        if (clears[field.key]) values[field.key] = "";
        else if (draft && draft.trim()) values[field.key] = draft.trim();
      }
      const clear = source.fields.filter((f) => clears[f.key]).map((f) => f.key);
      const updated = await api.saveCredentials(source.source, { values, clear });
      setView(updated);
      setDrafts((prev) => {
        const next = { ...prev };
        source.fields.forEach((f) => delete next[f.key]);
        return next;
      });
      setClears((prev) => {
        const next = { ...prev };
        source.fields.forEach((f) => delete next[f.key]);
        return next;
      });
      const ready = updated.sources.find((s) => s.source === source.source)?.ready;
      setMessage(
        ready
          ? `${source.label}: токены сохранены. Теперь можно нажать «Проверить подключение».`
          : `${source.label}: сохранено частично — не хватает ещё некоторых значений.`
      );
    } catch (err) {
      handleError(err);
    } finally {
      setSaving(null);
    }
  }

  async function test() {
    setTesting(true);
    setError(null);
    setMessage(null);
    setTests(null);
    try {
      const result = await api.testCredentials();
      const map: Record<string, { ok: boolean; message: string }> = {};
      result.sources.forEach((s) => (map[s.source] = { ok: s.ok, message: s.message }));
      setTests(map);
      const allOk = result.sources.every((s) => s.ok);
      setMessage(allOk ? "Оба подключения работают." : "Проверка выполнена — смотрите результат по каждому сервису ниже.");
    } catch (err) {
      handleError(err);
    } finally {
      setTesting(false);
    }
  }

  const mockMode = view?.mock_mode ?? false;

  return (
    <div className="stack">
      {mockMode && (
        <div className="banner banner-warn">
          Сейчас включён демо-режим: статистика берётся из тестовых данных, реальные API не вызываются. Токены
          сохранятся, но начнут использоваться только после отключения демо-режима.
        </div>
      )}
      {needKey && (
        <div className="banner banner-warn">
          Сервер требует ключ доступа к API.
          <div className="row" style={{ marginTop: 10 }}>
            <input
              type="text"
              style={{ maxWidth: 320 }}
              value={keyDraft}
              onChange={(e) => setKeyDraft(e.target.value)}
              placeholder="Ключ доступа"
            />
            <button
              className="btn btn-ghost"
              onClick={() => {
                setApiKey(keyDraft);
                setNeedKey(false);
              }}
            >
              Сохранить
            </button>
          </div>
        </div>
      )}
      {error && <div className="banner banner-error">{error}</div>}
      {message && !error && <div className="banner banner-ok">{message}</div>}

      {(view?.sources ?? []).map((source) => {
        const test = tests?.[source.source];
        return (
          <div className="card" key={source.source}>
            <div className="row space-between">
              <h2>
                {source.label}{" "}
                <span className={source.ready ? "pill pill-ok" : "pill"}>
                  {source.ready ? "заполнено" : "не заполнено"}
                </span>
              </h2>
            </div>
            <div className="form-grid">
              {source.fields.map((field) => (
                <div className="field" key={field.key}>
                  <label htmlFor={field.key}>{field.label}</label>
                  <input
                    id={field.key}
                    type={field.secret ? "password" : "text"}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder={
                      clears[field.key]
                        ? "Будет удалено при сохранении"
                        : field.filled
                        ? `Сохранено: ${field.preview} — вставьте новое, чтобы заменить`
                        : "Вставьте значение"
                    }
                    value={drafts[field.key] ?? ""}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  />
                  <small>{field.hint}</small>
                  {field.filled && (
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={!!clears[field.key]}
                        onChange={(e) => setClears((prev) => ({ ...prev, [field.key]: e.target.checked }))}
                      />
                      удалить сохранённое значение
                    </label>
                  )}
                </div>
              ))}
            </div>
            <div className="row" style={{ marginTop: 16 }}>
              <button className="btn btn-primary" onClick={() => save(source)} disabled={saving === source.source}>
                {saving === source.source && <span className="spinner" />}
                Сохранить {source.label}
              </button>
              {test && (
                <span className={test.ok ? "text-ok" : "text-bad"}>
                  {test.ok ? "✓ подключение работает" : `✗ ${test.message}`}
                </span>
              )}
            </div>
          </div>
        );
      })}

      <div className="card">
        <h2>Проверка подключения</h2>
        <p className="muted">
          Обращается к API только за служебной информацией аккаунта — ставки, бюджеты и кампании не меняются.
        </p>
        <button className="btn btn-ghost" onClick={test} disabled={testing}>
          {testing && <span className="spinner" />}
          {testing ? "Проверяю…" : "Проверить подключение"}
        </button>
        {view?.storage_note && <small className="muted" style={{ display: "block", marginTop: 12 }}>{view.storage_note}</small>}
      </div>
    </div>
  );
}
