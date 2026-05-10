// ========================================
// Batch console + PII Min UI + Settings
// ========================================

const BatchConsole = ({ goto }) => {
  const [running, setRunning] = uS(true);
  const [progress, setProgress] = uS(86.7);

  uE(() => {
    if (!running) return;
    const t = setInterval(() => {
      setProgress(p => Math.min(99, p + 0.3));
    }, 700);
    return () => clearInterval(t);
  }, [running]);

  return (
    <>
      <Topbar
        crumbs={["批次處理"]}
        actions={
          <>
            <Button icon={running ? "pause" : "play"} onClick={() => setRunning(!running)}>
              {running ? "暫停" : "繼續"}
            </Button>
            <Button icon="refresh">重新掃描 Drive</Button>
          </>
        }
      />
      <div className="content">
        <div className="page fade-in">
          <div className="page-head">
            <div>
              <h1>批次處理控制台</h1>
              <div className="desc">113-2 下學期 ・ 中斷後可恢復、教師編輯不被覆蓋</div>
            </div>
          </div>

          {/* main progress card */}
          <Card padding={0} style={{ marginBottom: 18 }}>
            <div style={{ padding: "20px 24px", borderBottom: "1px solid var(--line-1)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                <div>
                  <div style={{ fontFamily: "var(--serif)", fontSize: 18, fontWeight: 600 }}>
                    {running ? "處理中" : "已暫停"}
                    <span className={`badge ${running ? "processing" : "pending"}`} style={{ marginLeft: 10, verticalAlign: "middle" }}>
                      <span className="dot"/>{running ? "running" : "paused"}
                    </span>
                  </div>
                  <div className="muted sm" style={{ marginTop: 2 }}>
                    開始於 20:14 ・ 預計剩餘 12 分鐘 ・ 並行度 4
                  </div>
                </div>
                <div className="tnum" style={{ fontFamily: "var(--serif)", fontSize: 36, fontWeight: 600 }}>
                  {progress.toFixed(1)}<span style={{ fontSize: 18, color: "var(--ink-3)" }}>%</span>
                </div>
              </div>
              <div className="progress" style={{ height: 10 }}>
                <span style={{ width: `${progress}%` }}/>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)" }}>
              {[
                { l: "完成", v: "1,163", c: "var(--state-processed)" },
                { l: "進行中", v: "4", c: "var(--state-processing)" },
                { l: "待處理", v: "168", c: "var(--state-pending)" },
                { l: "失敗", v: "7", c: "var(--state-failed)" },
                { l: "已花費", v: "$0.82", c: "var(--ink-0)" },
              ].map((s, i) => (
                <div key={i} style={{
                  padding: "16px 22px",
                  borderRight: i < 4 ? "1px solid var(--line-1)" : "none",
                }}>
                  <div className="tnum" style={{
                    fontSize: 22, fontFamily: "var(--serif)", fontWeight: 600, color: s.c,
                  }}>{s.v}</div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{s.l}</div>
                </div>
              ))}
            </div>
          </Card>

          {/* reprocess pending — confirmation */}
          <div style={{ marginBottom: 18 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 10 }}>
              <h2 style={{ fontFamily: "var(--serif)", fontSize: 16, fontWeight: 600 }}>待你決定 ・ 3 件</h2>
              <span className="muted sm">原檔已更新,選擇覆蓋或保留你的編輯</span>
            </div>
            <Card padding={0}>
              {BATCH_REPROCESS.map((it, i) => (
                <div key={i} style={{
                  padding: "14px 22px",
                  borderBottom: i < BATCH_REPROCESS.length - 1 ? "1px solid var(--line-1)" : "none",
                  display: "flex", alignItems: "center", gap: 14,
                  background: it.edited ? "var(--state-edited-bg)" : "var(--paper-0)",
                  opacity: it.edited ? 1 : 0.95,
                }}>
                  <Icon name={fileIcon(it.name)} size={18} style={{ color: "var(--state-reprocess)" }}/>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="mono" style={{ fontSize: 12.5, fontWeight: 500, color: "var(--ink-0)" }}>
                      {it.name}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 4, display: "flex", gap: 12 }}>
                      {it.edited && <span style={{ color: "var(--state-edited)", fontWeight: 600 }}>✏️ 你已修改此檔</span>}
                      <span>{it.reason}</span>
                      <span className="muted">原 hash → 新 hash</span>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <Button size="sm">保留我的編輯</Button>
                    <Button size="sm" variant="primary">覆蓋重做</Button>
                  </div>
                </div>
              ))}
            </Card>
          </div>

          {/* live queue */}
          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 18 }}>
            <Card padding={0}>
              <div style={{ padding: "14px 22px", borderBottom: "1px solid var(--line-1)" }}>
                <div style={{ fontFamily: "var(--serif)", fontSize: 15, fontWeight: 600 }}>進行中 ・ 4 件</div>
                <div className="muted sm" style={{ marginTop: 2 }}>並行 worker 即時處理</div>
              </div>
              <div>
                {BATCH_QUEUE_NOW.map((it, i) => (
                  <div key={i} style={{
                    padding: "12px 22px",
                    borderBottom: i < BATCH_QUEUE_NOW.length - 1 ? "1px solid var(--line-1)" : "none",
                    display: "flex", alignItems: "center", gap: 12,
                  }}>
                    <Icon name={fileIcon(it.name)} size={14} style={{ color: "var(--state-processing)" }}/>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="mono" style={{ fontSize: 12, color: "var(--ink-1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {it.name}
                      </div>
                      <div className="muted sm mono" style={{ marginTop: 2 }}>{it.tier}</div>
                    </div>
                    <span className="tnum" style={{ fontSize: 11, color: "var(--ink-3)" }}>{it.elapsed}</span>
                    <div style={{
                      width: 14, height: 14, borderRadius: "50%",
                      border: "2px solid var(--line-2)",
                      borderTopColor: "var(--state-processing)",
                      animation: "spin 700ms linear infinite",
                    }}/>
                  </div>
                ))}
              </div>
            </Card>

            <Card padding={0}>
              <div style={{ padding: "14px 22px", borderBottom: "1px solid var(--line-1)" }}>
                <div style={{ fontFamily: "var(--serif)", fontSize: 15, fontWeight: 600 }}>失敗 ・ 7 件</div>
                <div className="muted sm" style={{ marginTop: 2 }}>已達重試上限,可手動重新處理</div>
              </div>
              <div>
                {[
                  { name: "S014/教師與學生互動紀錄/04月課堂錄音.m4a", reason: "音訊長度超過 30 分鐘", retry: 3 },
                  { name: "S022/作品成果/scan-002.pdf", reason: "OCR 解析失敗", retry: 3 },
                  { name: "S007/學習紀錄/截圖.heic", reason: "格式無法讀取", retry: 2 },
                ].map((it, i) => (
                  <div key={i} style={{
                    padding: "12px 22px",
                    borderBottom: i < 2 ? "1px solid var(--line-1)" : "none",
                    display: "flex", alignItems: "center", gap: 12,
                  }}>
                    <Icon name={fileIcon(it.name)} size={14} style={{ color: "var(--state-failed)" }}/>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="mono" style={{ fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.name}</div>
                      <div className="sm" style={{ color: "var(--state-failed)", marginTop: 2 }}>{it.reason} ・ 重試 {it.retry}/3</div>
                    </div>
                    <Button size="sm" icon="refresh">重試</Button>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
};

// ========== PII Min UI ==========
const PIIScreen = ({ goto }) => {
  const [search, setSearch] = uS("");
  const [editingId, setEditingId] = uS(null);
  const filtered = PII_MAPPING.filter(p =>
    !search || p.ps.includes(search.toUpperCase()) || (p.real && p.real.includes(search))
  );
  return (
    <>
      <Topbar
        crumbs={["PII 替換"]}
        actions={
          <>
            <div style={{ position: "relative" }}>
              <Icon name="search" size={14} style={{ position: "absolute", left: 10, top: 9, color: "var(--ink-3)" }}/>
              <input className="input" placeholder="搜尋代號或原值" value={search}
                onChange={(e) => setSearch(e.target.value)} style={{ paddingLeft: 30, width: 220 }}/>
            </div>
            <Button icon="plus">新增手動映射</Button>
          </>
        }
      />
      <div className="content">
        <div className="page fade-in">
          <div className="page-head">
            <div>
              <h1>PII 替換 Mapping</h1>
              <div className="desc">所有送 LLM 的內容都經過此映射表 — 你看到的是顯示名,LLM 看到的是代號。原值經 AES-256 加密本地保存。</div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <Segmented value="all" onChange={() => {}} options={[
                { value: "all", label: "全部" },
                { value: "auto", label: "自動" },
                { value: "manual", label: "手動" },
              ]}/>
            </div>
          </div>

          {/* stats */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 22 }}>
            <StatTile label="總映射數" value="124" sub="113 自動 + 11 手動"/>
            <StatTile label="本月匿名化" value="3,847" sub="次 PII 替換"/>
            <StatTile label="本月還原" value="3,847" sub="100% 對稱還原"/>
            <StatTile label="audit log" value="1,628" sub="LLM 呼叫紀錄"/>
          </div>

          <InlineHint icon="shield">
            <strong>系統會強制執行</strong> — 任何送 OpenRouter 的請求都會經過此映射層,無法繞過。
            原值欄位以對稱金鑰加密,金鑰存放於環境變數,不寫入程式碼或 LLM context。
          </InlineHint>

          <div style={{ marginTop: 16 }}>
            <Card padding={0}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Pseudonym</th>
                    <th>類型</th>
                    <th>顯示名</th>
                    <th>原值（已解密）</th>
                    <th>來源</th>
                    <th>動作</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p, i) => (
                    <tr key={i}>
                      <td>
                        <span className="mono" style={{
                          background: "var(--accent-bg)", color: "var(--accent-ink)",
                          padding: "2px 8px", borderRadius: 4, fontWeight: 600, fontSize: 12,
                        }}>{p.ps}</span>
                      </td>
                      <td className="muted sm">
                        {p.type === "student_name" ? "學生姓名" :
                         p.type === "parent_name" ? "家長姓名" :
                         p.type === "other_name" ? "其他人名" :
                         p.type === "phone" ? "電話" :
                         p.type === "email" ? "Email" : p.type}
                      </td>
                      <td>
                        {editingId === i ? (
                          <input className="input" defaultValue={p.display === "—" ? "" : p.display}
                            autoFocus onBlur={() => setEditingId(null)}
                            onKeyDown={(e) => e.key === "Enter" && setEditingId(null)}
                            style={{ width: 160 }}/>
                        ) : (
                          <span style={{ fontFamily: p.display === "—" ? "var(--mono)" : "var(--serif)" }}>{p.display}</span>
                        )}
                      </td>
                      <td>
                        <span style={{ fontFamily: "var(--serif)", fontSize: 13.5 }}>{p.real}</span>
                        <Icon name="lock" size={11} style={{ marginLeft: 6, color: "var(--ink-3)", verticalAlign: "-1px" }}/>
                      </td>
                      <td>
                        <span style={{
                          fontSize: 11, padding: "2px 8px", borderRadius: 999,
                          background: p.source === "manual" ? "var(--state-edited-bg)" : "var(--paper-1)",
                          color: p.source === "manual" ? "var(--state-edited)" : "var(--ink-2)",
                          fontWeight: 500,
                        }}>{p.source}</span>
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: 6 }}>
                          {(p.type === "student_name" || p.type === "other_name") && (
                            <Button size="sm" variant="ghost" icon="edit" onClick={() => setEditingId(i)}>改顯示名</Button>
                          )}
                          {p.source === "manual" && (
                            <Button size="sm" variant="ghost" icon="x">刪除</Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
};

// ========== Settings ==========
const Settings = () => {
  const [tab, setTab] = uS("models");
  const [tierConfig, setTierConfig] = uS(
    LLM_TIERS.reduce((acc, t) => ({ ...acc, [t.key]: t.model }), {})
  );

  return (
    <>
      <Topbar crumbs={["設定"]}/>
      <div className="content">
        <div className="page fade-in">
          <div className="page-head">
            <div>
              <h1>設定</h1>
              <div className="desc">LLM 模型路由、PII 規則、預算上限、帳號與授權</div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 28 }}>
            <nav style={{ display: "flex", flexDirection: "column", gap: 2, position: "sticky", top: 0, alignSelf: "flex-start" }}>
              {[
                { k: "models", l: "LLM 模型路由", i: "cpu" },
                { k: "folder", l: "資料夾對應", i: "layers" },
                { k: "budget", l: "預算上限", i: "dollar" },
                { k: "consent", l: "Attestation 紀錄", i: "shield" },
                { k: "account", l: "帳號 ・ 授權", i: "user" },
              ].map(it => (
                <div key={it.k} className="nav-item" data-active={tab === it.k} onClick={() => setTab(it.k)}>
                  <Icon name={it.i} className="ico"/>
                  <span>{it.l}</span>
                </div>
              ))}
            </nav>

            <div>
              {tab === "models" && (
                <Card padding={24}>
                  <div style={{ fontFamily: "var(--serif)", fontSize: 17, fontWeight: 600, marginBottom: 4 }}>LLM 模型路由</div>
                  <div className="muted sm" style={{ marginBottom: 18 }}>
                    每個 tier 對應的模型可獨立調整。預設為 Gemini 2.5 Flash Lite — 全部走最便宜選項約 $1 / 學期。
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    {LLM_TIERS.map(t => (
                      <div key={t.key} style={{
                        display: "grid", gridTemplateColumns: "200px 1fr 100px",
                        gap: 16, alignItems: "center",
                        padding: "14px 0", borderBottom: "1px solid var(--line-1)",
                      }}>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: 13 }}>{t.name}</div>
                          <div className="muted sm" style={{ marginTop: 2 }}>{t.desc}</div>
                          <div className="mono sm muted" style={{ marginTop: 2, fontSize: 11 }}>{t.key}</div>
                        </div>
                        <select
                          className="select"
                          value={tierConfig[t.key]}
                          onChange={(e) => setTierConfig({ ...tierConfig, [t.key]: e.target.value })}
                        >
                          {MODEL_OPTIONS.map(m => <option key={m} value={m}>{m}</option>)}
                        </select>
                        <div className="tnum muted sm" style={{ textAlign: "right" }}>{t.price}</div>
                      </div>
                    ))}
                  </div>

                  <InlineHint icon="info" tone="default">
                    <strong>data-policy: no-training</strong> — V1 預設模型承諾不用於訓練。切換模型前請確認該模型的資料政策。
                  </InlineHint>
                </Card>
              )}

              {tab === "folder" && (
                <Card padding={24}>
                  <div style={{ fontFamily: "var(--serif)", fontSize: 17, fontWeight: 600, marginBottom: 4 }}>資料夾對應</div>
                  <div className="muted sm" style={{ marginBottom: 18 }}>
                    系統將 Drive 中你的命名對應到三個標準類別。修改後會在下次掃描套用。
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {STANDARD_CATS.map(c => (
                      <div key={c.key} style={{
                        display: "grid", gridTemplateColumns: "1fr 24px 1fr",
                        gap: 14, alignItems: "center",
                        padding: "12px 14px",
                        background: "var(--paper-1)", borderRadius: "var(--r-2)",
                      }}>
                        <div>
                          <div className="muted sm">標準類別</div>
                          <div style={{ fontWeight: 500 }}>{c.name}</div>
                        </div>
                        <Icon name="arrowLeft" size={14} style={{ color: "var(--ink-3)", justifySelf: "center" }}/>
                        <div>
                          <div className="muted sm">你的命名</div>
                          <div className="mono" style={{ fontSize: 13 }}>
                            {c.key === "learning" ? "課堂筆記" : c.key === "interaction" ? "晤談紀錄" : "報告作品"}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: 18 }}>
                    <Button icon="refresh">重設對應</Button>
                  </div>
                </Card>
              )}

              {tab === "budget" && (
                <Card padding={24}>
                  <div style={{ fontFamily: "var(--serif)", fontSize: 17, fontWeight: 600, marginBottom: 4 }}>每月預算上限</div>
                  <div className="muted sm" style={{ marginBottom: 22 }}>
                    超過上限會自動暫停批次處理。可隨時調整。
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
                    <Card padding={20} style={{ background: "var(--paper-1)" }}>
                      <div className="muted sm">本月已花費</div>
                      <div className="tnum" style={{
                        fontFamily: "var(--serif)", fontSize: 36, fontWeight: 600, marginTop: 4,
                      }}>${TEACHER.budget_used.toFixed(2)}</div>
                      <div className="progress" style={{ marginTop: 12 }}>
                        <span style={{ width: `${(TEACHER.budget_used / TEACHER.budget_monthly) * 100}%` }}/>
                      </div>
                      <div className="muted sm tnum" style={{ marginTop: 6 }}>
                        / ${TEACHER.budget_monthly.toFixed(2)} 上限 ・ {((TEACHER.budget_used / TEACHER.budget_monthly) * 100).toFixed(1)}%
                      </div>
                    </Card>
                    <div>
                      <label style={{ fontSize: 13, fontWeight: 500, marginBottom: 6, display: "block" }}>每月上限 (USD)</label>
                      <input className="input" type="number" defaultValue={TEACHER.budget_monthly} step={0.5}/>
                      <div className="muted sm" style={{ marginTop: 16, lineHeight: 1.7 }}>
                        ・ Flash Lite 預估 ~$1.04/學期<br/>
                        ・ 升級到 Flash 約 +$0.16<br/>
                        ・ 升級到 Sonnet 約 +$0.46
                      </div>
                    </div>
                  </div>
                </Card>
              )}

              {tab === "consent" && (
                <Card padding={24}>
                  <div style={{ fontFamily: "var(--serif)", fontSize: 17, fontWeight: 600, marginBottom: 4 }}>家長同意聲明紀錄</div>
                  <div className="muted sm" style={{ marginBottom: 18 }}>
                    每次 attestation 文字版本變動時,會要求重新確認。以下為你目前生效的紀錄。
                  </div>
                  <div style={{
                    padding: 18, background: "var(--paper-1)",
                    borderRadius: "var(--r-2)", border: "1px solid var(--line-1)",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                      <Icon name="check" size={16} style={{ color: "var(--state-processed)" }}/>
                      <strong style={{ fontSize: 14 }}>已勾選 ・ 版本 v1</strong>
                      <span className="muted sm tnum" style={{ marginLeft: "auto" }}>2026-08-20 09:14</span>
                    </div>
                    <div style={{ fontFamily: "var(--serif)", fontSize: 13.5, lineHeight: 1.85, color: "var(--ink-2)" }}>
                      我聲明:對於我即將上傳到本系統處理的學生資料,我已依照所屬教育機構之規定取得適當的家長/監護人同意,並對學生個資的處理負起最終責任⋯⋯
                    </div>
                  </div>
                  <div style={{ marginTop: 14 }}>
                    <Button icon="refresh">重新確認</Button>
                  </div>
                </Card>
              )}

              {tab === "account" && (
                <Card padding={24}>
                  <div style={{ fontFamily: "var(--serif)", fontSize: 17, fontWeight: 600, marginBottom: 18 }}>帳號 ・ 授權</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 14, padding: 14, background: "var(--paper-1)", borderRadius: "var(--r-2)" }}>
                    <Avatar name="陳" size={48}/>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600 }}>{TEACHER.name} 老師</div>
                      <div className="muted sm">{TEACHER.email} ・ {TEACHER.school}</div>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <Button>登出</Button>
                      <Button>Revoke 授權</Button>
                    </div>
                  </div>
                  <hr className="divider"/>
                  <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>授權範圍</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12.5 }}>
                    <div className="mono" style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>drive.readonly</span><span className="muted">只讀 Drive 內容</span>
                    </div>
                    <div className="mono" style={{ display: "flex", justifyContent: "space-between" }}>
                      <span>openid email profile</span><span className="muted">識別你的帳號</span>
                    </div>
                  </div>
                  <hr className="divider"/>
                  <div className="muted sm">refresh token 以 AES-256 加密存儲於本機 SQLite,絕不傳送至任何外部服務。</div>
                </Card>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

window.BatchConsole = BatchConsole;
window.PIIScreen = PIIScreen;
window.SettingsScreen = Settings;
