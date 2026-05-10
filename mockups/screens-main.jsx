// ========================================
// Main app screens — Dashboard / Students / Files / Evaluation / Batch / PII / Settings
// ========================================

const { useState: uS, useEffect: uE, useMemo: uM, useRef: uR } = React;

// ========== Dashboard ==========
const Dashboard = ({ goto }) => {
  return (
    <>
      <Topbar
        crumbs={["總覽"]}
        actions={
          <>
            <Button icon="refresh" size="sm">重新掃描</Button>
            <Button icon="sparkle" variant="accent" onClick={() => goto("evaluation")}>產生評語</Button>
          </>
        }
      />
      <div className="content">
        <div className="page fade-in">
          <div className="page-head">
            <div>
              <h1>113-2 下學期 ・ 進行中</h1>
              <div className="desc">2026/02 - 2026/06 ・ 38 位學生 ・ 距離期末評語約 6 週</div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <Segmented
                value="113-2"
                onChange={() => {}}
                options={[
                  { value: "113-2", label: "113-2" },
                  { value: "113-1", label: "113-1" },
                  { value: "112-2", label: "112-2" },
                ]}
              />
            </div>
          </div>

          {/* stat tiles */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 24 }}>
            <StatTile label="學生" value="38" sub="本學期班級總人數"/>
            <StatTile label="素材處理" value="1163 / 1342" sub="86.7% 完成 ・ 4 進行中"/>
            <StatTile label="待你決定" value="3" sub="原檔已更新,等候你選擇" accent/>
            <StatTile label="本月成本" value="$1.34" sub={`預算上限 $${TEACHER.budget_monthly.toFixed(2)} ・ 26.8%`}/>
          </div>

          {/* main grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 18 }}>
            <Card padding={0}>
              <div style={{
                padding: "16px 22px", borderBottom: "1px solid var(--line-1)",
                display: "flex", alignItems: "center", justifyContent: "space-between",
              }}>
                <div>
                  <div style={{ fontFamily: "var(--serif)", fontSize: 16, fontWeight: 600 }}>批次處理進行中</div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>113-2 下學期 ・ 從 20:14 開始 ・ 預計剩餘 12 分鐘</div>
                </div>
                <Button icon="cpu" onClick={() => goto("batch")}>查看詳情</Button>
              </div>

              <div style={{ padding: 22 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                  <span style={{ fontSize: 13, color: "var(--ink-2)" }}>
                    <strong className="tnum" style={{ color: "var(--ink-0)" }}>1,163</strong>
                    <span style={{ color: "var(--ink-3)" }}> / 1,342</span>
                  </span>
                  <span style={{ display: "flex", gap: 12, fontSize: 12 }}>
                    <span style={{ color: "var(--state-processed)" }}>● 完成 1163</span>
                    <span style={{ color: "var(--state-processing)" }}>● 進行中 4</span>
                    <span style={{ color: "var(--state-failed)" }}>● 失敗 7</span>
                  </span>
                </div>
                <div className="progress" style={{ height: 10 }}>
                  <span style={{ width: "86.7%" }}/>
                </div>

                <div style={{
                  marginTop: 18,
                  display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8,
                }}>
                  {BATCH_QUEUE_NOW.slice(0, 4).map((it, i) => (
                    <div key={i} style={{
                      display: "flex", gap: 10, alignItems: "center",
                      padding: "8px 10px",
                      background: "var(--paper-1)",
                      borderRadius: 6,
                      fontSize: 12,
                      minWidth: 0,
                    }}>
                      <Icon name={fileIcon(it.name)} size={14} style={{ color: "var(--ink-3)", flex: "0 0 14px" }}/>
                      <span className="mono" style={{
                        flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        color: "var(--ink-1)",
                      }}>{it.name}</span>
                      <span className="tnum" style={{ color: "var(--ink-3)", fontSize: 11 }}>{it.elapsed}</span>
                    </div>
                  ))}
                </div>
              </div>
            </Card>

            <Card padding={0}>
              <div style={{
                padding: "16px 22px", borderBottom: "1px solid var(--line-1)",
              }}>
                <div style={{ fontFamily: "var(--serif)", fontSize: 16, fontWeight: 600 }}>待你決定 ・ 3 件</div>
                <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>原檔有更新,等待你選擇覆蓋或保留編輯</div>
              </div>
              <div style={{ padding: "8px 0" }}>
                {BATCH_REPROCESS.map((it, i) => (
                  <div key={i} style={{
                    display: "flex", gap: 10, alignItems: "center",
                    padding: "10px 22px",
                    borderBottom: i < BATCH_REPROCESS.length - 1 ? "1px solid var(--line-1)" : "none",
                  }}>
                    <Icon name={fileIcon(it.name)} size={14} style={{ color: "var(--state-reprocess)" }}/>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="mono" style={{ fontSize: 12, color: "var(--ink-1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {it.name}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>
                        {it.edited && <span style={{ color: "var(--state-edited)", marginRight: 6 }}>✏️ 你已修改</span>}
                        {it.reason}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ padding: "12px 22px", borderTop: "1px solid var(--line-1)" }}>
                <Button onClick={() => goto("batch")} style={{ width: "100%" }}>逐件審核</Button>
              </div>
            </Card>
          </div>

          {/* recent students */}
          <div style={{ marginTop: 24 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <h2 style={{ fontFamily: "var(--serif)", fontSize: 18, fontWeight: 600 }}>近期活動</h2>
              <Button variant="ghost" size="sm" onClick={() => goto("students")}>
                全部學生 <Icon name="arrowRight" size={12}/>
              </Button>
            </div>
            <Card padding={0}>
              <table className="table">
                <thead>
                  <tr>
                    <th>學生</th>
                    <th>素材</th>
                    <th>進度</th>
                    <th>編輯</th>
                    <th>近況</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {STUDENTS.slice(0, 6).map(s => (
                    <tr key={s.pseudo} onClick={() => goto("student", s.pseudo)} style={{ cursor: "pointer" }}>
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <Avatar name={s.display} size={28}/>
                          <div>
                            <div style={{ fontWeight: 500 }}>{s.display} <span className="muted mono sm">{s.pseudo}</span></div>
                            <div className="muted sm">{s.note}</div>
                          </div>
                        </div>
                      </td>
                      <td className="tnum">{s.files}</td>
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <div className="progress" style={{ width: 80 }}>
                            <span style={{ width: `${(s.processed / s.files) * 100}%` }}/>
                          </div>
                          <span className="muted sm tnum">{Math.round((s.processed / s.files) * 100)}%</span>
                        </div>
                      </td>
                      <td>{s.edited > 0 ? <StateBadge state="edited" count={s.edited}/> : <span className="muted">—</span>}</td>
                      <td className="muted sm">{s.last}</td>
                      <td><Icon name="chevronRight" size={14} style={{ color: "var(--ink-3)" }}/></td>
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

// ========== Students list ==========
const Students = ({ goto }) => {
  const [view, setView] = uS("grid");
  const [search, setSearch] = uS("");
  const filtered = STUDENTS.filter(s =>
    !search || s.display.includes(search) || s.pseudo.includes(search.toUpperCase()) || s.real.includes(search)
  );
  return (
    <>
      <Topbar
        crumbs={["學生"]}
        actions={
          <>
            <div style={{ position: "relative" }}>
              <Icon name="search" size={14} style={{ position: "absolute", left: 10, top: 9, color: "var(--ink-3)" }}/>
              <input className="input" placeholder="搜尋姓名或代號" value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ paddingLeft: 30, width: 220 }}/>
            </div>
            <Segmented value={view} onChange={setView} options={[
              { value: "grid", label: "卡片" },
              { value: "list", label: "清單" },
            ]}/>
          </>
        }
      />
      <div className="content">
        <div className="page fade-in">
          <div className="page-head">
            <div>
              <h1>學生 ・ 113-2 下學期</h1>
              <div className="desc">點擊學生可查看本學期的三類素材與處理狀態。系統送 LLM 時使用代號(S001..),你看到的是顯示名。</div>
            </div>
          </div>

          {view === "grid" ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
              {filtered.map(s => (
                <Card key={s.pseudo} padding={18} hover onClick={() => goto("student", s.pseudo)}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                    <Avatar name={s.display} size={40}/>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontFamily: "var(--serif)" }}>{s.display}</div>
                      <div className="mono sm muted">{s.pseudo}</div>
                    </div>
                    {s.edited > 0 && <StateBadge state="edited" count={s.edited}/>}
                  </div>
                  <div className="muted sm" style={{ marginBottom: 10, lineHeight: 1.5, minHeight: 36 }}>{s.note}</div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12 }}>
                    <span className="muted tnum">{s.processed}/{s.files} 處理</span>
                    <span className="muted">{s.last}</span>
                  </div>
                  <div className="progress" style={{ marginTop: 8 }}>
                    <span style={{ width: `${(s.processed / s.files) * 100}%` }}/>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <Card padding={0}>
              <table className="table">
                <thead>
                  <tr>
                    <th>學生</th><th>代號</th><th>素材</th><th>進度</th><th>編輯</th><th>更新</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(s => (
                    <tr key={s.pseudo} onClick={() => goto("student", s.pseudo)} style={{ cursor: "pointer" }}>
                      <td><div style={{ display: "flex", alignItems: "center", gap: 10 }}><Avatar name={s.display} size={28}/><span style={{ fontWeight: 500 }}>{s.display}</span></div></td>
                      <td className="mono sm muted">{s.pseudo}</td>
                      <td className="tnum">{s.files}</td>
                      <td><div className="progress" style={{ width: 100 }}><span style={{ width: `${(s.processed/s.files)*100}%` }}/></div></td>
                      <td>{s.edited > 0 ? <StateBadge state="edited" count={s.edited}/> : <span className="muted">—</span>}</td>
                      <td className="muted sm">{s.last}</td>
                      <td><Icon name="chevronRight" size={14} style={{ color: "var(--ink-3)" }}/></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      </div>
    </>
  );
};

// ========== Student detail ==========
const StudentDetail = ({ pseudo, goto }) => {
  const s = STUDENTS.find(s => s.pseudo === pseudo) || STUDENTS[0];
  const [cat, setCat] = uS("learning");
  const files = FILES_ZIHAN[cat] || [];

  return (
    <>
      <Topbar
        crumbs={["學生", s.display]}
        actions={
          <>
            <Button icon="download" size="sm">下載整包</Button>
            <Button icon="sparkle" variant="accent" onClick={() => goto("evaluation", s.pseudo)}>產生本學期評語</Button>
          </>
        }
      />
      <div className="content">
        <div className="page fade-in">
          <div style={{ display: "flex", gap: 18, alignItems: "flex-start", marginBottom: 22 }}>
            <Avatar name={s.display} size={64}/>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                <h1 style={{ fontFamily: "var(--serif)", fontSize: 28, fontWeight: 600 }}>{s.display}</h1>
                <span className="mono muted" style={{ fontSize: 13 }}>{s.pseudo}</span>
                <span className="muted sm">・ {s.real}</span>
              </div>
              <div className="muted" style={{ marginTop: 6, fontSize: 13.5 }}>{s.note}</div>
              <div style={{ display: "flex", gap: 14, marginTop: 12, fontSize: 12, color: "var(--ink-2)" }}>
                <span><strong className="tnum" style={{ color: "var(--ink-0)" }}>{s.files}</strong> 個素材</span>
                <span><strong className="tnum" style={{ color: "var(--ink-0)" }}>{s.processed}</strong> 已處理</span>
                <span><strong className="tnum" style={{ color: "var(--ink-0)" }}>{s.edited}</strong> 教師編輯</span>
                <span>最後更新 {s.last}</span>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
            {CATEGORIES.map(c => {
              const count = (FILES_ZIHAN[c.key] || []).length;
              return (
                <button key={c.key} onClick={() => setCat(c.key)} style={{
                  display: "flex", gap: 10, alignItems: "center",
                  padding: "12px 16px",
                  background: cat === c.key ? "var(--paper-0)" : "var(--paper-1)",
                  border: "1px solid " + (cat === c.key ? "var(--ink-1)" : "var(--line-1)"),
                  borderRadius: "var(--r-2)",
                  flex: 1,
                  textAlign: "left",
                  transition: "all 100ms",
                  cursor: "pointer",
                }}>
                  <Icon name={c.icon} size={20} style={{ color: cat === c.key ? "var(--accent)" : "var(--ink-3)" }}/>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</div>
                    <div className="muted sm">{c.desc}</div>
                  </div>
                  <div style={{ fontSize: 18, fontFamily: "var(--serif)", fontWeight: 600 }} className="tnum">{count}</div>
                </button>
              );
            })}
          </div>

          <Card padding={0}>
            <table className="table">
              <thead>
                <tr>
                  <th></th><th>檔名</th><th>大小</th><th>修改時間</th><th>處理狀態</th><th>tier</th><th></th>
                </tr>
              </thead>
              <tbody>
                {files.map(f => (
                  <tr key={f.id} onClick={() => goto("file", f.id)} style={{ cursor: "pointer" }}>
                    <td style={{ width: 36 }}><Icon name={fileIcon(f.name)} size={16} style={{ color: "var(--ink-3)" }}/></td>
                    <td>
                      <div style={{ fontWeight: 500 }}>{f.name}</div>
                      {f.duration && <div className="muted sm tnum">{f.duration} ・ {f.speakers} 講者</div>}
                      {f.fail && <div className="sm" style={{ color: "var(--state-failed)" }}>{f.fail}</div>}
                    </td>
                    <td className="muted sm tnum">{f.size}</td>
                    <td className="muted sm tnum">{f.mtime}</td>
                    <td><StateBadge state={f.state}/></td>
                    <td className="mono sm muted">{f.tier}</td>
                    <td><Icon name="chevronRight" size={14} style={{ color: "var(--ink-3)" }}/></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </div>
    </>
  );
};

window.Dashboard = Dashboard;
window.Students = Students;
window.StudentDetail = StudentDetail;
