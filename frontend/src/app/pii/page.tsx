'use client';

import { useEffect, useState } from 'react';
import { ApiError, api, type PIIMappingRow, type PIIType } from '@/lib/api';

const PII_TYPE_LABELS: Record<string, string> = {
  student_name: '學生姓名',
  student_id: '學號',
  parent_name: '家長姓名',
  phone: '電話',
  email: '電子郵件',
  address: '住址',
  other_name: '其他姓名',
  other: '其他',
};

export default function PIIPage() {
  const [rows, setRows] = useState<PIIMappingRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ pseudonym: string; value: string } | null>(null);
  const [aliasForm, setAliasForm] = useState({
    pseudonym: '',
    original_value: '',
    pii_type: 'student_name' as PIIType,
  });

  async function reload() {
    setError(null);
    try {
      const data = await api.listPIIMappings();
      setRows(data);
    } catch (err) {
      setError(formatError(err));
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function saveDisplay() {
    if (!editing) return;
    try {
      await api.updatePIIDisplayName(editing.pseudonym, editing.value || null);
      setEditing(null);
      await reload();
    } catch (err) {
      setError(formatError(err));
    }
  }

  async function addAlias() {
    if (!aliasForm.pseudonym || !aliasForm.original_value) return;
    try {
      await api.addManualPIIMapping(aliasForm);
      setAliasForm({ pseudonym: '', original_value: '', pii_type: 'student_name' });
      await reload();
    } catch (err) {
      setError(formatError(err));
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">PII 對應管理</h1>
      <p className="text-sm text-ink-muted">
        所有送 LLM 之前都會替換為下列 pseudonym；可改顯示名稱、新增別名（同一人多種寫法）。
      </p>

      {error && (
        <div className="rounded border border-warn/40 bg-warn/5 px-3 py-2 text-warn text-sm">
          {error}
        </div>
      )}

      {/* Existing mappings */}
      <section className="rounded-md border border-stone-200 bg-white p-4">
        <h2 className="mb-3 font-semibold">現有對應</h2>
        {rows === null ? (
          <p className="text-sm text-ink-muted">載入中…</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-ink-muted">尚無對應。執行批次處理後會自動偵測。</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-ink-muted">
              <tr>
                <th className="py-1">Pseudonym</th>
                <th className="py-1">類型</th>
                <th className="py-1">原值</th>
                <th className="py-1">顯示名（教師可改）</th>
                <th className="py-1">來源</th>
                <th className="py-1"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="py-2 font-mono text-xs">{row.pseudonym}</td>
                  <td className="py-2">{PII_TYPE_LABELS[row.pii_type] ?? row.pii_type}</td>
                  <td className="py-2 text-ink-muted">{row.original_value ?? '（解密失敗）'}</td>
                  <td className="py-2">
                    {editing?.pseudonym === row.pseudonym ? (
                      <input
                        className="rounded border border-stone-300 px-2 py-1 text-sm w-full"
                        value={editing.value}
                        onChange={(e) =>
                          setEditing({ pseudonym: row.pseudonym, value: e.target.value })
                        }
                        placeholder="留白以清除"
                      />
                    ) : (
                      row.display_name ?? <span className="text-ink-muted">（未設定）</span>
                    )}
                  </td>
                  <td className="py-2 text-xs text-ink-muted">{row.source}</td>
                  <td className="py-2 text-right">
                    {editing?.pseudonym === row.pseudonym ? (
                      <>
                        <button
                          type="button"
                          onClick={saveDisplay}
                          className="text-accent text-xs underline mr-2"
                        >
                          儲存
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditing(null)}
                          className="text-ink-muted text-xs underline"
                        >
                          取消
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        onClick={() =>
                          setEditing({
                            pseudonym: row.pseudonym,
                            value: row.display_name ?? '',
                          })
                        }
                        className="text-accent text-xs underline"
                      >
                        編輯
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Add alias form */}
      <section className="rounded-md border border-stone-200 bg-white p-4 space-y-3">
        <h2 className="font-semibold">手動新增別名</h2>
        <p className="text-sm text-ink-muted">
          將另一種寫法（例：暱稱、英文名）綁定到既有 pseudonym。
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <label className="flex flex-col">
            既有 Pseudonym
            <input
              className="mt-1 rounded border border-stone-300 px-2 py-1 font-mono"
              value={aliasForm.pseudonym}
              onChange={(e) => setAliasForm({ ...aliasForm, pseudonym: e.target.value })}
              placeholder="例：S001"
            />
          </label>
          <label className="flex flex-col">
            原值（要對應的另一種寫法）
            <input
              className="mt-1 rounded border border-stone-300 px-2 py-1"
              value={aliasForm.original_value}
              onChange={(e) =>
                setAliasForm({ ...aliasForm, original_value: e.target.value })
              }
              placeholder="例：阿明"
            />
          </label>
          <label className="flex flex-col">
            類型
            <select
              className="mt-1 rounded border border-stone-300 px-2 py-1"
              value={aliasForm.pii_type}
              onChange={(e) =>
                setAliasForm({ ...aliasForm, pii_type: e.target.value as PIIType })
              }
            >
              {Object.entries(PII_TYPE_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button
          type="button"
          onClick={addAlias}
          disabled={!aliasForm.pseudonym || !aliasForm.original_value}
          className="rounded-md bg-accent text-white px-4 py-1.5 disabled:opacity-50"
        >
          新增別名
        </button>
      </section>
    </div>
  );
}

function formatError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.reason === 'invalid_pseudonym') return '此 pseudonym 不存在，請先使用 anonymize 偵測它。';
    if (err.reason === 'pseudonym_not_found') return '找不到該 pseudonym。';
    if (err.status === 401) return '工作階段已逾時，請重新登入。';
    return `${err.message}（${err.status}）`;
  }
  return err instanceof Error ? err.message : String(err);
}
