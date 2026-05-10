'use client';

import { useEffect, useState } from 'react';
import { ApiError, api, type SettingsResponse } from '@/lib/api';

const TIER_LABELS: Record<string, string> = {
  summary_cheap: '文件摘要（summary_cheap）',
  vision_cheap: '影像摘要（vision_cheap）',
  audio_standard: '音訊轉寫（audio_standard）',
  evaluation_quality: '學期評語（evaluation_quality）',
};

const DEFAULT_MODEL = 'google/gemini-2.5-flash-lite';

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function reload() {
    setError(null);
    try {
      const s = await api.getSettings();
      setSettings(s);
      // Pre-fill overrides with current values (so UI shows what's effective)
      setOverrides(s.llm_tier_config);
    } catch (err) {
      setError(formatError(err));
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function save() {
    setSaving(true);
    setSaved(false);
    setError(null);
    // Convert "use default" (= matches default) into "" so the backend clears the override
    const toSend: Record<string, string> = {};
    for (const [tier, value] of Object.entries(overrides)) {
      toSend[tier] = value === DEFAULT_MODEL ? '' : value;
    }
    try {
      await api.updateTierConfig(toSend);
      setSaved(true);
      await reload();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setSaving(false);
    }
  }

  if (!settings) {
    return <p className="text-ink-muted">載入中…</p>;
  }

  const usagePct = (settings.monthly_cost_usd / settings.monthly_budget_usd) * 100;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">設定</h1>

      {error && (
        <div className="rounded border border-warn/40 bg-warn/5 px-3 py-2 text-warn text-sm">
          {error}
        </div>
      )}
      {saved && (
        <div className="rounded border border-accent/40 bg-accent/5 px-3 py-2 text-accent text-sm">
          已儲存。
        </div>
      )}

      {/* Budget gauge */}
      <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
        <h2 className="font-semibold">本月 LLM 用量</h2>
        <div className="flex items-baseline justify-between text-sm">
          <span>
            US${settings.monthly_cost_usd.toFixed(5)} /{' '}
            US${settings.monthly_budget_usd.toFixed(2)}
          </span>
          <span className="text-ink-muted">{usagePct.toFixed(1)}%</span>
        </div>
        <div className="h-3 overflow-hidden rounded bg-stone-200">
          <div
            className={`h-full ${usagePct >= 100 ? 'bg-warn' : 'bg-accent'}`}
            style={{ width: `${Math.min(usagePct, 100)}%` }}
          />
        </div>
        <p className="text-xs text-ink-muted">
          月預算為 process-wide 設定（env: BUDGET_MONTHLY_USD）。
        </p>
      </section>

      {/* LLM tier overrides */}
      <section className="space-y-3 rounded-md border border-stone-200 bg-white p-4">
        <h2 className="font-semibold">LLM tier 覆寫</h2>
        <p className="text-sm text-ink-muted">
          設為「{DEFAULT_MODEL}」會使用系統預設（清除個人覆寫）。
        </p>
        <table className="w-full text-sm">
          <thead className="text-left text-ink-muted">
            <tr>
              <th className="py-1">Tier</th>
              <th className="py-1">使用模型</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {Object.entries(TIER_LABELS).map(([tier, label]) => (
              <tr key={tier}>
                <td className="py-2">{label}</td>
                <td className="py-2">
                  <input
                    className="w-full rounded border border-stone-300 px-2 py-1 font-mono text-xs"
                    value={overrides[tier] ?? DEFAULT_MODEL}
                    onChange={(e) =>
                      setOverrides({ ...overrides, [tier]: e.target.value })
                    }
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="rounded-md bg-accent text-white px-4 py-1.5 disabled:opacity-50"
        >
          {saving ? '儲存中…' : '儲存覆寫'}
        </button>
      </section>

      {/* Account / logout */}
      <section className="rounded-md border border-stone-200 bg-white p-4 space-y-2">
        <h2 className="font-semibold">帳號</h2>
        <button
          type="button"
          onClick={async () => {
            await api.logout();
            window.location.href = '/';
          }}
          className="rounded-md border border-warn text-warn px-3 py-1.5 text-sm hover:bg-warn/5"
        >
          登出
        </button>
      </section>
    </div>
  );
}

function formatError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return '工作階段已逾時，請重新登入。';
    if (err.reason === 'invalid_tier') return `無效的 tier：${err.message}`;
    return `${err.message}（${err.status}）`;
  }
  return err instanceof Error ? err.message : String(err);
}
