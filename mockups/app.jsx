// ========================================
// App shell + routing
// ========================================

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#c1452a",
  "fontPair": "serif-sans",
  "density": 1,
  "theme": "light"
}/*EDITMODE-END*/;

const ACCENT_OPTIONS = [
  ["#c1452a", "#e87557", "#f7e9e2"],   // 朱砂(預設)
  ["#2d5d5e", "#4a8688", "#dde9e9"],   // 墨綠
  ["#3a4d6b", "#6580a3", "#dde3ed"],   // 藏青
  ["#7a4a89", "#a37cb0", "#ebdef0"],   // 紫
];

const App = () => {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [route, setRoute] = uS("dashboard");
  const [routeArg, setRouteArg] = uS(null);
  const [onboarded, setOnboarded] = uS(true);

  uE(() => {
    document.documentElement.setAttribute("data-theme", t.theme);
    const accent = Array.isArray(t.accent) ? t.accent[0] : t.accent;
    const accentSoft = Array.isArray(t.accent) ? t.accent[1] : t.accent;
    const accentBg = Array.isArray(t.accent) ? t.accent[2] : "var(--paper-1)";
    document.documentElement.style.setProperty("--accent", accent);
    document.documentElement.style.setProperty("--accent-soft", accentSoft);
    document.documentElement.style.setProperty("--accent-bg", accentBg);
    document.documentElement.style.setProperty("--dens", t.density);
    if (t.fontPair === "sans-only") {
      document.documentElement.style.setProperty("--serif", "var(--sans)");
    } else {
      document.documentElement.style.setProperty("--serif", '"Noto Serif TC", "Source Han Serif TC", ui-serif, Georgia, serif');
    }
  }, [t]);

  const goto = (r, arg) => { setRoute(r); setRouteArg(arg); };

  if (!onboarded) {
    return (
      <>
        <Onboarding onComplete={() => setOnboarded(true)}/>
        <TweaksPanel title="Tweaks" defaults={TWEAK_DEFAULTS}>
          <TweakSection title="外觀">
            <TweakColor label="主色" value={t.accent} options={ACCENT_OPTIONS}
              onChange={(v) => setTweak("accent", v)}/>
            <TweakRadio label="主題" value={t.theme} options={[
              { value: "light", label: "淺色" }, { value: "dark", label: "深色" },
            ]} onChange={(v) => setTweak("theme", v)}/>
          </TweakSection>
          <TweakSection title="跳到 Onboarding">
            <TweakButton onClick={() => setOnboarded(false)}>重新體驗 onboarding</TweakButton>
            <TweakButton onClick={() => setOnboarded(true)}>跳過進入主畫面</TweakButton>
          </TweakSection>
        </TweaksPanel>
      </>
    );
  }

  let screen = null;
  if (route === "dashboard") screen = <Dashboard goto={goto}/>;
  else if (route === "students") screen = <Students goto={goto}/>;
  else if (route === "student") screen = <StudentDetail pseudo={routeArg} goto={goto}/>;
  else if (route === "files") screen = <Students goto={goto}/>;
  else if (route === "file") screen = <FileDetail fileId={routeArg} goto={goto}/>;
  else if (route === "evaluation") screen = <EvaluationGenerator pseudo={routeArg} goto={goto}/>;
  else if (route === "batch") screen = <BatchConsole goto={goto}/>;
  else if (route === "pii") screen = <PIIScreen goto={goto}/>;
  else if (route === "settings") screen = <SettingsScreen/>;
  else screen = <Dashboard goto={goto}/>;

  return (
    <>
      <div className="app">
        <Sidebar route={route} onNavigate={(r) => goto(r)}/>
        <div className="main">{screen}</div>
      </div>

      <TweaksPanel title="Tweaks" defaults={TWEAK_DEFAULTS}>
        <TweakSection title="外觀">
          <TweakColor label="主色"
            value={t.accent}
            options={ACCENT_OPTIONS}
            onChange={(v) => setTweak("accent", v)}/>
          <TweakRadio label="主題" value={t.theme} options={[
            { value: "light", label: "淺色" },
            { value: "dark", label: "深色" },
          ]} onChange={(v) => setTweak("theme", v)}/>
          <TweakRadio label="字型" value={t.fontPair} options={[
            { value: "serif-sans", label: "襯線+無襯線" },
            { value: "sans-only", label: "全無襯線" },
          ]} onChange={(v) => setTweak("fontPair", v)}/>
          <TweakSlider label="資訊密度" value={t.density} min={0.85} max={1.2} step={0.05}
            onChange={(v) => setTweak("density", v)}/>
        </TweakSection>
        <TweakSection title="跳到流程">
          <TweakButton onClick={() => setOnboarded(false)}>重新體驗 onboarding</TweakButton>
          <TweakButton onClick={() => goto("evaluation")}>評語生成器(Hero)</TweakButton>
          <TweakButton onClick={() => goto("batch")}>批次處理控制台</TweakButton>
          <TweakButton onClick={() => goto("file", "f1")}>單一檔案頁</TweakButton>
        </TweakSection>
      </TweaksPanel>
    </>
  );
};

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
