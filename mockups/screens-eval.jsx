// ========================================
// Evaluation generator (HERO) + File detail
// ========================================

const STYLE_OPTIONS = [
  {
    key: "formal",
    name: "正式",
    desc: "成績單 / 行政文件",
    long: "正式語氣,少情感詞,重實事陳述,適合官方紀錄",
    color: "#3a4d6b",
  },
  {
    key: "encouraging",
    name: "鼓勵",
    desc: "家長日 / 給學生本人",
    long: "溫暖鼓勵,強調成長與潛力,適合與家長分享",
    color: "#c1452a",
  },
  {
    key: "objective",
    name: "客觀",
    desc: "事件導向 / 觀察紀錄",
    long: "以觀察事實為主,少詮釋,仍保持建設性",
    color: "#2f7a4d",
  },
];

const EvaluationGenerator = ({ pseudo, goto }) => {
  const initialStudent = pseudo ? STUDENTS.find(s => s.pseudo === pseudo) : STUDENTS[0];
  const [selPseudo, setSelPseudo] = uS(initialStudent.pseudo);
  const student = STUDENTS.find(s => s.pseudo === selPseudo) || STUDENTS[0];

  const [seed, setSeed] = uS(SAMPLE_EVAL_SEED);
  const [style, setStyle] = uS("encouraging");
  const [generating, setGenerating] = uS(false);
  const [result, setResult] = uS(SAMPLE_EVAL_OUTPUT);
  const [showAnonymized, setShowAnonymized] = uS(false);
  const [history, setHistory] = uS([
    { ts: "5 分鐘前", style: "encouraging", chars: result.length },
  ]);
  const seedLen = seed.length;

  const generate = () => {
    setGenerating(true);
    setTimeout(() => {
      setGenerating(false);
      setResult(SAMPLE_EVAL_OUTPUT);
      setHistory([{ ts: "剛剛", style, chars: SAMPLE_EVAL_OUTPUT.length }, ...history]);
    }, 1800);
  };

  const sources = [
    { icon: "book", cat: "學習紀錄", count: 8, sample: "週記-W12-反思閱讀的力量" },
    { icon: "chat", cat: "教師與學生互動紀錄", count: 5, sample: "10月晤談-關於閱讀偏好" },
    { icon: "star", cat: "作品成果", count: 5, sample: "期末報告-台灣文學中的女性形象" },
  ];

  // anonymized preview — replace display names with pseudo IDs
  const anonymizedSeed = seed
    .replace(/子涵/g, "S001")
    .replace(/老師/g, "T001");

  return (
    <>
      <Topbar
        crumbs={["評語生成"]}
        actions={
          <>
            <select className="select" value={selPseudo} onChange={(e) => setSelPseudo(e.target.value)} style={{ width: 200 }}>
              {STUDENTS.map(s => <option key={s.pseudo} value={s.pseudo}>{s.display}（{s.pseudo}）</option>)}
            </select>
            <Button icon="download" disabled={!result}>下載 .txt</Button>
            <Button icon="check" variant="primary" disabled={!result}>儲存定稿</Button>
          </>
        }
      />
      <div className="content">
        <div className="fade-in" style={{
          maxWidth: 1320, margin: "0 auto", padding: "var(--pad-5)",
          display: "grid", gridTemplateColumns: "380px 1fr", gap: 20,
        }}>
          {/* LEFT — input panel */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Card padding={20}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
                <Avatar name={student.display} size={44}/>
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: "var(--serif)", fontSize: 18, fontWeight: 600 }}>
                    {student.display}
                    <span className="mono muted" style={{ fontSize: 12, marginLeft: 8 }}>{student.pseudo}</span>
                  </div>
                  <div className="muted sm">113-2 下學期</div>
                </div>
              </div>
              <div style={{
                display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8,
              }}>
                {sources.map((src, i) => (
                  <div key={i} style={{
                    background: "var(--paper-1)",
                    padding: "10px 12px", borderRadius: 8,
                  }}>
                    <Icon name={src.icon} size={14} style={{ color: "var(--ink-3)" }}/>
                    <div className="tnum" style={{ fontFamily: "var(--serif)", fontSize: 22, fontWeight: 600, lineHeight: 1, marginTop: 6 }}>{src.count}</div>
                    <div className="muted" style={{ fontSize: 11, marginTop: 2, lineHeight: 1.3 }}>{src.cat}</div>
                  </div>
                ))}
              </div>
            </Card>

            <Card padding={20}>
              <label style={{
                display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6,
              }}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>評價種子</span>
                <span style={{ fontSize: 11, color: seedLen >= 30 && seedLen <= 100 ? "var(--state-processed)" : "var(--ink-3)" }} className="tnum">
                  {seedLen} / 30-100 字
                </span>
              </label>
              <textarea
                className="textarea"
                rows={8}
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                placeholder="用 30-100 字寫下你對這位學生本學期的整體觀察。系統會根據這個方向,從素材中找具體例子撰寫。"
                style={{ fontFamily: "var(--serif)", fontSize: 14, lineHeight: 1.7 }}
              />
              <div className="muted" style={{ fontSize: 11.5, marginTop: 8, display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="info" size={12}/>
                你的種子定方向,LLM 補充具體事件與引用 — 不會虛構素材中沒有的事
              </div>
            </Card>

            <Card padding={20}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>風格</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {STYLE_OPTIONS.map(opt => (
                  <label key={opt.key} style={{
                    display: "flex", gap: 12, alignItems: "flex-start",
                    padding: "10px 12px",
                    border: "1px solid " + (style === opt.key ? opt.color : "var(--line-1)"),
                    borderRadius: "var(--r-2)",
                    background: style === opt.key ? "var(--paper-1)" : "var(--paper-0)",
                    cursor: "pointer",
                    transition: "all 80ms",
                    position: "relative",
                  }}>
                    <input type="radio" name="style" checked={style === opt.key}
                      onChange={() => setStyle(opt.key)}
                      style={{ marginTop: 2, accentColor: opt.color }}/>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>
                        {opt.name}
                        <span style={{ fontSize: 11.5, color: "var(--ink-3)", marginLeft: 8, fontWeight: 400 }}>
                          {opt.desc}
                        </span>
                      </div>
                      <div className="muted" style={{ fontSize: 11.5, marginTop: 3, lineHeight: 1.5 }}>{opt.long}</div>
                    </div>
                  </label>
                ))}
              </div>
            </Card>

            <Button
              variant="accent" size="lg" icon="sparkle" onClick={generate}
              disabled={generating || seedLen < 10}
              style={{ justifyContent: "center", padding: "12px 16px" }}
            >
              {generating ? "生成中⋯⋯" : "生成評語"}
            </Button>

            <div style={{
              padding: "10px 12px", background: "var(--paper-1)",
              borderRadius: "var(--r-2)", fontSize: 11.5, color: "var(--ink-3)",
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <Icon name="dollar" size={12}/>
              <span>單次生成預估 <span className="tnum" style={{ color: "var(--ink-1)", fontWeight: 600 }}>$0.0008</span></span>
              <span style={{ marginLeft: "auto" }}>tier: <span className="mono">evaluation_quality</span></span>
            </div>
          </div>

          {/* RIGHT — output */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>
            {/* PII anonymization preview */}
            <Card padding={0} style={{ background: "var(--paper-1)", borderColor: "var(--line-1)" }}>
              <div style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "10px 16px", borderBottom: "1px solid var(--line-1)",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                  <Icon name="shield" size={14} style={{ color: "var(--accent)" }}/>
                  <strong>送出前匿名化預覽</strong>
                  <span className="muted">— 系統實際送 LLM 的內容</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className="muted sm">顯示</span>
                  <Segmented
                    value={showAnonymized ? "anon" : "real"}
                    onChange={(v) => setShowAnonymized(v === "anon")}
                    options={[
                      { value: "real", label: "你看到的" },
                      { value: "anon", label: "LLM 看到的" },
                    ]}
                  />
                </div>
              </div>
              <div style={{
                padding: 16, fontSize: 12.5, fontFamily: "var(--serif)",
                lineHeight: 1.75, color: "var(--ink-1)",
                fontVariantNumeric: "tabular-nums",
              }}>
                {showAnonymized
                  ? <span dangerouslySetInnerHTML={{ __html:
                      anonymizedSeed.replace(/(S001|T001)/g, '<span class="mono" style="background:var(--accent-bg);color:var(--accent-ink);padding:1px 5px;border-radius:3px;font-size:11.5px">$1</span>')
                    }}/>
                  : <span>{seed}</span>}
              </div>
            </Card>

            {/* result */}
            <Card padding={0} style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 460 }}>
              <div style={{
                padding: "14px 22px", borderBottom: "1px solid var(--line-1)",
                display: "flex", alignItems: "center", justifyContent: "space-between",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ fontFamily: "var(--serif)", fontSize: 15, fontWeight: 600 }}>評語初稿</div>
                  {!generating && result && (
                    <span className="badge processed">
                      <span className="dot"/>
                      已生成 ・ {STYLE_OPTIONS.find(s => s.key === style)?.name} ・ <span className="tnum">{result.length}</span> 字
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <Button size="sm" icon="refresh" onClick={generate} disabled={generating}>重新生成</Button>
                </div>
              </div>

              {generating ? (
                <div style={{ padding: 60, textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
                  <div style={{
                    width: 40, height: 40, borderRadius: "50%",
                    background: "var(--paper-1)",
                    border: "2px solid var(--line-2)",
                    borderTopColor: "var(--accent)",
                    animation: "spin 700ms linear infinite",
                  }}/>
                  <div className="muted">正在閱讀 18 份素材,撰寫初稿⋯⋯</div>
                  <div className="muted sm" style={{ fontFamily: "var(--mono)" }}>evaluation_quality ・ google/gemini-2.5-flash-lite</div>
                </div>
              ) : (
                <div style={{ padding: "24px 28px", flex: 1, overflow: "auto" }}>
                  <textarea
                    className="textarea"
                    value={result}
                    onChange={(e) => setResult(e.target.value)}
                    style={{
                      width: "100%", height: 360,
                      fontFamily: "var(--serif)",
                      fontSize: 16.5,
                      lineHeight: 2,
                      letterSpacing: "0.02em",
                      padding: 20,
                      background: "var(--paper-0)",
                      border: "1px solid var(--line-1)",
                      resize: "vertical",
                    }}
                  />
                </div>
              )}

              {!generating && result && (
                <div style={{
                  padding: "10px 22px", borderTop: "1px solid var(--line-1)",
                  display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12,
                  background: "var(--paper-1)",
                }}>
                  <div className="muted" style={{ display: "flex", gap: 14 }}>
                    <span>引用素材 <strong className="tnum" style={{ color: "var(--ink-1)" }}>3</strong> 處</span>
                    <span>編輯 <strong className="tnum" style={{ color: "var(--ink-1)" }}>0</strong> 字</span>
                    <span>成本 <strong className="tnum" style={{ color: "var(--ink-1)" }}>$0.0008</strong></span>
                  </div>
                  <div className="muted">字數為 prompt 軟限制,系統不做硬性截斷</div>
                </div>
              )}
            </Card>

            {history.length > 0 && (
              <Card padding={16}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: "var(--ink-2)" }}>本次工作階段歷史</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {history.map((h, i) => (
                    <div key={i} style={{ display: "flex", gap: 10, fontSize: 12, color: "var(--ink-2)" }}>
                      <span className="mono muted" style={{ width: 80 }}>{h.ts}</span>
                      <span style={{ width: 70 }}>{STYLE_OPTIONS.find(s => s.key === h.style)?.name}</span>
                      <span className="tnum muted">{h.chars} 字</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

// ========== File detail ==========
const FileDetail = ({ fileId, goto }) => {
  // find file across categories
  const allFiles = [].concat(FILES_ZIHAN.learning, FILES_ZIHAN.interaction, FILES_ZIHAN.work);
  const f = allFiles.find(x => x.id === fileId) || allFiles[0];
  const isAudio = f.tier === "audio_standard";
  const md = isAudio ? SAMPLE_TRANSCRIPT : SAMPLE_MD;
  const [content, setContent] = uS(md);
  const [edited, setEdited] = uS(false);

  return (
    <>
      <Topbar
        crumbs={["學生", "子涵", f.name]}
        actions={
          <>
            <Button icon="download" size="sm">下載原檔</Button>
            <Button icon="refresh" size="sm">重新處理</Button>
            <Button icon="check" variant="primary" disabled={!edited}>儲存編輯</Button>
          </>
        }
      />
      <div className="content">
        <div className="fade-in" style={{
          maxWidth: 1280, margin: "0 auto", padding: "var(--pad-5)",
          display: "grid", gridTemplateColumns: "320px 1fr", gap: 20,
        }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Card padding={18}>
              <Icon name={fileIcon(f.name)} size={32} style={{ color: "var(--ink-3)", marginBottom: 12 }}/>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6, wordBreak: "break-all" }}>{f.name}</div>
              <StateBadge state={f.state}/>

              <div style={{ marginTop: 16, fontSize: 12, color: "var(--ink-2)", lineHeight: 1.9 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span className="muted">大小</span><span className="tnum">{f.size}</span></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span className="muted">修改</span><span className="tnum">{f.mtime}</span></div>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span className="muted">tier</span><span className="mono sm">{f.tier}</span></div>
                {f.duration && <div style={{ display: "flex", justifyContent: "space-between" }}><span className="muted">長度</span><span className="tnum">{f.duration}</span></div>}
                {f.speakers && <div style={{ display: "flex", justifyContent: "space-between" }}><span className="muted">講者</span><span className="tnum">{f.speakers}</span></div>}
                <div style={{ display: "flex", justifyContent: "space-between" }}><span className="muted">成本</span><span className="tnum">$0.0002</span></div>
              </div>
            </Card>

            <Card padding={18}>
              <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 10, color: "var(--ink-2)" }}>原檔資訊</div>
              <div style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.7 }}>
                <div className="mono sm muted" style={{ marginBottom: 4 }}>drive_path:</div>
                <div className="mono sm" style={{ wordBreak: "break-all" }}>/113-1/王子涵/{f.name.includes(".m4a") ? "教師與學生互動紀錄" : "學習紀錄"}/{f.name}</div>
                <div className="mono sm muted" style={{ marginTop: 8 }}>content_hash:</div>
                <div className="mono sm">a7f3c9d2...8b1e4f</div>
              </div>
            </Card>

            <Card padding={18}>
              <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 10, color: "var(--ink-2)" }}>PII 替換</div>
              <div className="muted sm" style={{ marginBottom: 8 }}>本檔處理時替換了 4 個 PII:</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {["S001", "T001", "T002", "S001"].map((p, i) => (
                  <span key={i} className="mono" style={{
                    fontSize: 10.5, padding: "1px 6px",
                    background: "var(--accent-bg)", color: "var(--accent-ink)",
                    borderRadius: 3,
                  }}>{p}</span>
                ))}
              </div>
            </Card>
          </div>

          <Card padding={0} style={{ display: "flex", flexDirection: "column" }}>
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "12px 22px", borderBottom: "1px solid var(--line-1)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontFamily: "var(--serif)", fontSize: 15, fontWeight: 600 }}>
                  {isAudio ? "逐字稿" : "Markdown 摘要"}
                </span>
                {edited && <StateBadge state="edited"/>}
              </div>
              <div className="muted sm">已自動儲存於 30 秒前</div>
            </div>
            <textarea
              value={content}
              onChange={(e) => { setContent(e.target.value); setEdited(true); }}
              style={{
                flex: 1, minHeight: 540,
                padding: "20px 28px",
                fontFamily: "var(--mono)",
                fontSize: 12.5, lineHeight: 1.75,
                background: "var(--paper-0)",
                border: "none", outline: "none", resize: "none",
                color: "var(--ink-1)",
              }}
            />
          </Card>
        </div>
      </div>
    </>
  );
};

window.EvaluationGenerator = EvaluationGenerator;
window.FileDetail = FileDetail;
