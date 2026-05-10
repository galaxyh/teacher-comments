// ========================================
// Onboarding 流程 — login → attestation → 根目錄 → mapping wizard
// ========================================

const ONB_STEPS = [
  { key: "login", label: "登入" },
  { key: "consent", label: "家長同意聲明" },
  { key: "root", label: "選擇教學資料根目錄" },
  { key: "mapping", label: "資料夾對應" },
  { key: "scan", label: "建立索引" },
];

const OnboardingShell = ({ step, children }) => {
  const idx = ONB_STEPS.findIndex(s => s.key === step);
  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--paper-1)",
      display: "grid",
      gridTemplateRows: "auto 1fr",
    }}>
      <header style={{
        padding: "16px 28px",
        borderBottom: "1px solid var(--line-1)",
        background: "var(--paper-0)",
        display: "flex",
        alignItems: "center",
        gap: 12,
      }}>
        <div className="logo" style={{
          width: 28, height: 28, borderRadius: 6,
          background: "var(--ink-0)", color: "var(--paper-0)",
          display: "grid", placeItems: "center",
          fontFamily: "var(--serif)", fontWeight: 600, fontSize: 15,
        }}>墨</div>
        <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 15 }}>墨痕</div>
        <div style={{ marginLeft: 24, display: "flex", gap: 4, alignItems: "center" }}>
          {ONB_STEPS.map((s, i) => (
            <React.Fragment key={s.key}>
              {i > 0 && <div style={{ width: 24, height: 1, background: i <= idx ? "var(--ink-2)" : "var(--line-2)" }}/>}
              <div style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "4px 10px",
                borderRadius: 999,
                fontSize: 12,
                background: i === idx ? "var(--ink-0)" : (i < idx ? "transparent" : "transparent"),
                color: i === idx ? "var(--paper-0)" : (i < idx ? "var(--ink-1)" : "var(--ink-3)"),
                fontWeight: i === idx ? 600 : 500,
              }}>
                {i < idx ? <Icon name="check" size={12}/> : <span className="tnum">{i + 1}</span>}
                {s.label}
              </div>
            </React.Fragment>
          ))}
        </div>
      </header>
      <main style={{ display: "grid", placeItems: "center", padding: 40 }}>
        <div className="fade-in" style={{ width: "100%", maxWidth: 580 }}>
          {children}
        </div>
      </main>
    </div>
  );
};

const ScreenLogin = ({ onNext }) => (
  <OnboardingShell step="login">
    <Card padding={36} style={{ textAlign: "center" }}>
      <div style={{
        width: 56, height: 56, borderRadius: 14,
        background: "var(--ink-0)", color: "var(--paper-0)",
        display: "grid", placeItems: "center", margin: "0 auto 16px",
        fontFamily: "var(--serif)", fontWeight: 600, fontSize: 26,
      }}>墨</div>
      <h1 style={{ fontFamily: "var(--serif)", fontSize: 26, fontWeight: 600, lineHeight: 1.3 }}>
        歡迎回到墨痕
      </h1>
      <div style={{ color: "var(--ink-2)", marginTop: 8, fontSize: 14, lineHeight: 1.7 }}>
        讓你的教學觀察,化為一句一句準確的學期評語。<br/>
        我們從你的 Google Drive 讀取教學素材,所有處理皆在你的個人實例中進行。
      </div>

      <button
        onClick={onNext}
        style={{
          marginTop: 28,
          width: "100%",
          padding: "12px 18px",
          background: "#fff",
          border: "1px solid var(--line-2)",
          borderRadius: "var(--r-2)",
          fontSize: 14,
          fontWeight: 500,
          color: "#3c4043",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
          boxShadow: "var(--sh-1)",
          cursor: "pointer",
        }}>
        <Icon name="google" size={18}/>
        使用 Google 帳號登入
      </button>

      <div style={{ marginTop: 16, fontSize: 11.5, color: "var(--ink-3)", lineHeight: 1.6 }}>
        我們僅請求 <span className="mono" style={{ background: "var(--paper-1)", padding: "1px 5px", borderRadius: 3 }}>drive.readonly</span> 權限。
        系統絕不會修改你的 Drive 內容。
      </div>

      <hr className="divider" style={{ margin: "24px 0 18px" }}/>

      <div style={{ display: "flex", justifyContent: "space-around", fontSize: 12, color: "var(--ink-2)" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <Icon name="lock" size={20} style={{ color: "var(--accent)" }}/>
          PII 匿名化前處理
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <Icon name="cpu" size={20} style={{ color: "var(--accent)" }}/>
          ~$1 / 學期成本
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
          <Icon name="edit" size={20} style={{ color: "var(--accent)" }}/>
          教師永遠最終定稿
        </div>
      </div>
    </Card>
  </OnboardingShell>
);

const ScreenConsent = ({ onNext, onBack }) => {
  const [checked, setChecked] = useState(false);
  return (
    <OnboardingShell step="consent">
      <Card padding={32}>
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 14 }}>
          <Icon name="shield" size={22} style={{ color: "var(--accent)" }}/>
          <h2 style={{ fontFamily: "var(--serif)", fontSize: 20, fontWeight: 600 }}>
            家長同意聲明
          </h2>
        </div>
        <div style={{ color: "var(--ink-2)", fontSize: 13.5, marginBottom: 16, lineHeight: 1.7 }}>
          這份聲明是法律與專業倫理的基礎。系統處理的是未成年學生資料,你作為教師需確認已取得適當的家長/監護人同意。
        </div>

        <div style={{
          background: "var(--paper-1)",
          padding: 18,
          borderRadius: "var(--r-2)",
          border: "1px solid var(--line-1)",
          fontFamily: "var(--serif)",
          fontSize: 14.5,
          lineHeight: 1.85,
          color: "var(--ink-1)",
          marginBottom: 18,
        }}>
          我聲明:對於我即將上傳到本系統處理的學生資料,我已依照所屬教育機構之規定取得適當的家長/監護人同意,並對學生個資的處理負起最終責任。
          <br/><br/>
          本系統僅為輔助工具,不替代我作為教師的法律與道德責任。學生個資(姓名、聯絡方式等)在送出系統邊界前,均會經過匿名化處理。
        </div>

        <label style={{
          display: "flex", gap: 10, alignItems: "flex-start",
          padding: 14,
          border: "1px solid " + (checked ? "var(--accent)" : "var(--line-2)"),
          borderRadius: "var(--r-2)",
          background: checked ? "var(--accent-bg)" : "var(--paper-0)",
          cursor: "pointer",
          transition: "background 120ms, border-color 120ms",
        }}>
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
            style={{ marginTop: 3, accentColor: "var(--accent)" }}
          />
          <div style={{ fontSize: 13.5, fontWeight: 500 }}>
            我已閱讀並同意上述聲明
            <div style={{ fontSize: 12, color: "var(--ink-2)", fontWeight: 400, marginTop: 2 }}>
              勾選紀錄會以時間戳記寫入稽核日誌(版本 v1)
            </div>
          </div>
        </label>

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 24 }}>
          <Button variant="ghost" onClick={onBack} icon="arrowLeft">取消(登出)</Button>
          <Button variant="accent" disabled={!checked} onClick={onNext}>
            我同意 <Icon name="arrowRight" size={14}/>
          </Button>
        </div>
      </Card>
    </OnboardingShell>
  );
};

const FOLDERS = [
  { id: "f1", name: "教學資料", path: "/我的雲端硬碟/教學資料", suggested: true, count: 1487 },
  { id: "f2", name: "備課", path: "/我的雲端硬碟/備課", count: 234 },
  { id: "f3", name: "個人文件", path: "/我的雲端硬碟/個人文件", count: 89 },
  { id: "f4", name: "研習進修", path: "/我的雲端硬碟/研習進修", count: 67 },
];

const ScreenRoot = ({ onNext, onBack }) => {
  const [selected, setSelected] = useState("f1");
  return (
    <OnboardingShell step="root">
      <Card padding={32}>
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 6 }}>
          <Icon name="drive" size={22}/>
          <h2 style={{ fontFamily: "var(--serif)", fontSize: 20, fontWeight: 600 }}>
            選擇教學資料根目錄
          </h2>
        </div>
        <div style={{ color: "var(--ink-2)", fontSize: 13, marginBottom: 18, lineHeight: 1.65 }}>
          系統會在這個資料夾下尋找「學期 → 學生 → 三類資料夾」的結構。
          標準命名為 <span className="mono">學習紀錄 / 教師與學生互動紀錄 / 作品成果</span>;
          若你目前的命名不同,下一步會引導對應。
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 18 }}>
          {FOLDERS.map(f => (
            <label key={f.id} style={{
              display: "flex", alignItems: "center", gap: 12,
              padding: "12px 14px",
              border: "1px solid " + (selected === f.id ? "var(--ink-1)" : "var(--line-1)"),
              background: selected === f.id ? "var(--paper-1)" : "var(--paper-0)",
              borderRadius: "var(--r-2)",
              cursor: "pointer",
              transition: "border-color 80ms, background 80ms",
            }}>
              <input
                type="radio"
                name="root"
                checked={selected === f.id}
                onChange={() => setSelected(f.id)}
                style={{ accentColor: "var(--ink-0)" }}
              />
              <Icon name="folder" size={18} style={{ color: "var(--ink-2)" }}/>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 14, fontWeight: 500 }}>{f.name}</span>
                  {f.suggested && (
                    <span style={{
                      fontSize: 10, padding: "1px 6px", borderRadius: 999,
                      background: "var(--accent-bg)", color: "var(--accent-ink)",
                      letterSpacing: "0.04em", fontWeight: 600,
                    }}>建議</span>
                  )}
                </div>
                <div className="mono" style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 2 }}>{f.path}</div>
              </div>
              <div className="tnum" style={{ fontSize: 12, color: "var(--ink-2)" }}>{f.count} 檔</div>
            </label>
          ))}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 16 }}>
          <Button variant="ghost" onClick={onBack} icon="arrowLeft">上一步</Button>
          <Button variant="primary" onClick={onNext}>
            繼續 <Icon name="arrowRight" size={14}/>
          </Button>
        </div>
      </Card>
    </OnboardingShell>
  );
};

const STANDARD_CATS = [
  { key: "learning", name: "學習紀錄" },
  { key: "interaction", name: "教師與學生互動紀錄" },
  { key: "work", name: "作品成果" },
];
const DETECTED_FOLDERS = ["課堂筆記", "晤談紀錄", "報告作品", "雜項"];

const ScreenMapping = ({ onNext, onBack }) => {
  const [mapping, setMapping] = useState({
    learning: "課堂筆記",
    interaction: "晤談紀錄",
    work: "報告作品",
  });
  return (
    <OnboardingShell step="mapping">
      <Card padding={32}>
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 6 }}>
          <Icon name="layers" size={22}/>
          <h2 style={{ fontFamily: "var(--serif)", fontSize: 20, fontWeight: 600 }}>
            資料夾對應
          </h2>
        </div>
        <div style={{ color: "var(--ink-2)", fontSize: 13, marginBottom: 16, lineHeight: 1.65 }}>
          我們在學生資料夾下偵測到以下子資料夾命名,請對應到三個標準類別:
        </div>

        <div style={{
          background: "var(--paper-1)",
          padding: "10px 14px",
          borderRadius: "var(--r-2)",
          fontSize: 12,
          color: "var(--ink-2)",
          marginBottom: 16,
          display: "flex", flexWrap: "wrap", gap: 8,
        }}>
          <span style={{ color: "var(--ink-3)", fontSize: 11 }}>偵測到:</span>
          {DETECTED_FOLDERS.map(f => (
            <span key={f} className="mono" style={{
              background: "var(--paper-0)", border: "1px solid var(--line-1)",
              padding: "2px 8px", borderRadius: 4, fontSize: 11.5,
            }}>{f}</span>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {STANDARD_CATS.map(cat => (
            <div key={cat.key} style={{
              display: "grid", gridTemplateColumns: "1fr auto 1fr",
              alignItems: "center", gap: 16,
              padding: "10px 14px",
              border: "1px solid var(--line-1)",
              borderRadius: "var(--r-2)",
              background: "var(--paper-0)",
            }}>
              <div style={{ fontSize: 13.5, fontWeight: 500 }}>
                <Icon name={cat.key === "learning" ? "book" : cat.key === "interaction" ? "chat" : "star"} size={14}
                  style={{ display: "inline-block", marginRight: 6, verticalAlign: "-2px", color: "var(--ink-3)" }}/>
                {cat.name}
              </div>
              <Icon name="arrowLeft" size={14} style={{ color: "var(--ink-3)" }}/>
              <select
                className="select"
                value={mapping[cat.key] || ""}
                onChange={(e) => setMapping({ ...mapping, [cat.key]: e.target.value })}
              >
                <option value="">— 不歸類 —</option>
                {DETECTED_FOLDERS.map(f => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 14, fontSize: 12, color: "var(--ink-3)", display: "flex", alignItems: "center", gap: 6 }}>
          <Icon name="info" size={14}/>
          未對應的子資料夾(例如「雜項」)將不會被處理。此對應關係將儲存於你的設定中,後續掃描自動套用。
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 24 }}>
          <Button variant="ghost" onClick={onBack} icon="arrowLeft">上一步</Button>
          <Button variant="primary" onClick={onNext}>
            儲存對應 <Icon name="arrowRight" size={14}/>
          </Button>
        </div>
      </Card>
    </OnboardingShell>
  );
};

const ScreenScan = ({ onNext }) => {
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState("scanning");

  useEffect(() => {
    let p = 0;
    const t = setInterval(() => {
      p = Math.min(100, p + 6);
      setProgress(p);
      if (p === 100) {
        clearInterval(t);
        setTimeout(() => setPhase("done"), 300);
      }
    }, 120);
    return () => clearInterval(t);
  }, []);

  return (
    <OnboardingShell step="scan">
      <Card padding={36} style={{ textAlign: "center" }}>
        {phase === "scanning" ? (
          <>
            <div style={{
              width: 56, height: 56, margin: "0 auto 16px",
              borderRadius: "50%", display: "grid", placeItems: "center",
              background: "var(--paper-1)",
              border: "2px solid var(--line-2)",
              borderTopColor: "var(--accent)",
              animation: "spin 800ms linear infinite",
            }}/>
            <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
            <h2 style={{ fontFamily: "var(--serif)", fontSize: 20, fontWeight: 600 }}>正在建立索引</h2>
            <div style={{ color: "var(--ink-2)", marginTop: 6, fontSize: 13 }}>
              掃描你的 Drive 結構,辨識學期、學生與三類資料夾⋯⋯
            </div>
            <div className="progress" style={{ marginTop: 22, marginBottom: 8 }}>
              <span style={{ width: `${progress}%` }}/>
            </div>
            <div className="tnum" style={{ fontSize: 12, color: "var(--ink-3)" }}>{progress}%</div>
          </>
        ) : (
          <>
            <div style={{
              width: 56, height: 56, margin: "0 auto 16px",
              borderRadius: "50%", display: "grid", placeItems: "center",
              background: "var(--state-processed-bg)",
              color: "var(--state-processed)",
            }}>
              <Icon name="check" size={28}/>
            </div>
            <h2 style={{ fontFamily: "var(--serif)", fontSize: 20, fontWeight: 600 }}>索引完成</h2>
            <div style={{ color: "var(--ink-2)", marginTop: 8, fontSize: 13.5, lineHeight: 1.7 }}>
              發現 <strong>3 個學期</strong>、<strong>38 位學生</strong>、<strong>1,487 個檔案</strong>。
            </div>
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 18,
            }}>
              {[
                { l: "文件", v: 1124 },
                { l: "圖片", v: 96 },
                { l: "音訊", v: 267 },
              ].map(it => (
                <div key={it.l} style={{
                  background: "var(--paper-1)", padding: 12, borderRadius: 8,
                }}>
                  <div className="tnum" style={{ fontSize: 22, fontWeight: 600, fontFamily: "var(--serif)" }}>{it.v}</div>
                  <div style={{ fontSize: 11, color: "var(--ink-3)" }}>{it.l}</div>
                </div>
              ))}
            </div>
            <Button variant="accent" onClick={onNext} style={{ marginTop: 24, width: "100%" }} size="lg">
              進入墨痕 <Icon name="arrowRight" size={14}/>
            </Button>
          </>
        )}
      </Card>
    </OnboardingShell>
  );
};

const Onboarding = ({ onComplete }) => {
  const [step, setStep] = useState("login");
  const order = ["login", "consent", "root", "mapping", "scan"];
  const next = () => {
    const i = order.indexOf(step);
    if (i < order.length - 1) setStep(order[i + 1]);
    else onComplete();
  };
  const back = () => {
    const i = order.indexOf(step);
    if (i > 0) setStep(order[i - 1]);
  };

  if (step === "login") return <ScreenLogin onNext={next}/>;
  if (step === "consent") return <ScreenConsent onNext={next} onBack={back}/>;
  if (step === "root") return <ScreenRoot onNext={next} onBack={back}/>;
  if (step === "mapping") return <ScreenMapping onNext={next} onBack={back}/>;
  if (step === "scan") return <ScreenScan onNext={onComplete}/>;
  return null;
};

window.Onboarding = Onboarding;
