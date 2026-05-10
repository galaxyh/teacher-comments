// ========================================
// 共用 UI 元件 — 教師評語系統
// ========================================

const { useState, useEffect, useRef, useMemo, useCallback } = React;

// ========== Badge ==========
const STATE_LABELS = {
  pending:    { cls: "pending",    label: "待處理" },
  processing: { cls: "processing", label: "處理中" },
  processed:  { cls: "processed",  label: "已處理" },
  edited:     { cls: "edited",     label: "已修改" },
  reprocess:  { cls: "reprocess",  label: "待你決定" },
  failed:     { cls: "failed",     label: "失敗" },
};

const StateBadge = ({ state, count, style }) => {
  const s = STATE_LABELS[state];
  if (!s) return null;
  return (
    <span className={`badge ${s.cls}`} style={style}>
      <span className="dot"/>
      {s.label}
      {count != null && <span className="tnum" style={{ marginLeft: 4, opacity: 0.7 }}>{count}</span>}
    </span>
  );
};

// ========== Button ==========
const Button = ({ variant = "default", size, icon, children, ...rest }) => {
  const cls = ["btn"];
  if (variant === "primary") cls.push("primary");
  else if (variant === "accent") cls.push("accent");
  else if (variant === "ghost") cls.push("ghost");
  if (size) cls.push(size);
  return (
    <button className={cls.join(" ")} {...rest}>
      {icon && <Icon name={icon} size={14}/>}
      {children}
    </button>
  );
};

// ========== Card ==========
const Card = ({ children, style, hover, onClick, padding = 20 }) => (
  <div
    className="card"
    onClick={onClick}
    style={{
      padding,
      cursor: onClick ? "pointer" : "default",
      transition: "box-shadow 120ms, border-color 120ms, transform 120ms",
      ...style,
    }}
    onMouseEnter={hover ? (e) => {
      e.currentTarget.style.boxShadow = "var(--sh-2)";
      e.currentTarget.style.borderColor = "var(--line-2)";
    } : undefined}
    onMouseLeave={hover ? (e) => {
      e.currentTarget.style.boxShadow = "var(--sh-1)";
      e.currentTarget.style.borderColor = "var(--line-1)";
    } : undefined}
  >
    {children}
  </div>
);

// ========== Segmented control ==========
const Segmented = ({ value, onChange, options }) => (
  <div className="seg">
    {options.map(o => (
      <button key={o.value} data-active={value === o.value} onClick={() => onChange(o.value)}>
        {o.label}
      </button>
    ))}
  </div>
);

// ========== Topbar ==========
const Topbar = ({ crumbs, actions }) => (
  <div className="topbar">
    <div className="crumbs">
      {crumbs.map((c, i) => (
        <React.Fragment key={i}>
          {i > 0 && <Icon name="chevronRight" size={12} className="sep"/>}
          <span className={i === crumbs.length - 1 ? "last" : ""}>{c}</span>
        </React.Fragment>
      ))}
    </div>
    <div className="topbar-actions">{actions}</div>
  </div>
);

// ========== StatTile ==========
const StatTile = ({ label, value, sub, accent }) => (
  <Card padding={18}>
    <div style={{ fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-3)", fontWeight: 600 }}>
      {label}
    </div>
    <div style={{
      fontFamily: "var(--serif)",
      fontSize: 30,
      fontWeight: 600,
      marginTop: 6,
      color: accent ? "var(--accent)" : "var(--ink-0)",
      letterSpacing: "-0.01em",
      lineHeight: 1.1,
    }} className="tnum">{value}</div>
    {sub && <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 4 }}>{sub}</div>}
  </Card>
);

// ========== Avatar ==========
const Avatar = ({ name, size = 30, color }) => {
  const ch = (name || "?").slice(0, 1);
  return (
    <div className="avatar" style={{
      width: size, height: size, fontSize: size * 0.42,
      background: color || "var(--accent-bg)",
      color: color ? "#fff" : "var(--accent-ink)",
    }}>{ch}</div>
  );
};

// ========== Sidebar ==========
const NAV_ITEMS = [
  { key: "dashboard", icon: "home", label: "總覽" },
  { key: "students", icon: "user", label: "學生", count: 38 },
  { key: "files", icon: "folder", label: "素材瀏覽" },
  { key: "evaluation", icon: "sparkle", label: "評語生成", highlight: true },
  { key: "batch", icon: "cpu", label: "批次處理" },
  { key: "pii", icon: "shield", label: "PII 替換" },
  { key: "settings", icon: "settings", label: "設定" },
];

const Sidebar = ({ route, onNavigate }) => (
  <aside className="sidebar">
    <div className="sidebar-brand">
      <div className="logo">墨</div>
      <div>
        <div className="name">墨痕</div>
        <div className="sub">TEACHER EVAL · v0.2</div>
      </div>
    </div>

    <nav className="sidebar-nav">
      <div className="nav-section-title">本學期 · 113-2</div>
      {NAV_ITEMS.slice(0, 5).map(it => (
        <div
          key={it.key}
          className="nav-item"
          data-active={route === it.key}
          onClick={() => onNavigate(it.key)}
        >
          <Icon name={it.icon} className="ico"/>
          <span>{it.label}</span>
          {it.highlight && route !== it.key && (
            <span style={{
              marginLeft: "auto",
              width: 6, height: 6,
              borderRadius: "50%",
              background: "var(--accent)",
            }}/>
          )}
          {it.count && <span className="count">{it.count}</span>}
        </div>
      ))}

      <div className="nav-section-title" style={{ marginTop: 10 }}>系統</div>
      {NAV_ITEMS.slice(5).map(it => (
        <div
          key={it.key}
          className="nav-item"
          data-active={route === it.key}
          onClick={() => onNavigate(it.key)}
        >
          <Icon name={it.icon} className="ico"/>
          <span>{it.label}</span>
        </div>
      ))}
    </nav>

    <div className="sidebar-foot">
      <div className="avatar">陳</div>
      <div className="info">
        <div className="n">陳芸老師</div>
        <div className="e">{TEACHER.email}</div>
      </div>
      <button className="btn ghost sm" style={{ padding: "4px 6px" }} title="登出">
        <Icon name="x" size={14}/>
      </button>
    </div>
  </aside>
);

// ========== Empty / Hint ==========
const InlineHint = ({ icon = "info", children, tone = "default" }) => {
  const bg = tone === "warn" ? "var(--state-reprocess-bg)" : tone === "danger" ? "var(--state-failed-bg)" : "var(--paper-1)";
  const fg = tone === "warn" ? "var(--state-reprocess)" : tone === "danger" ? "var(--state-failed)" : "var(--ink-2)";
  return (
    <div style={{
      display: "flex", gap: 10, alignItems: "flex-start",
      background: bg, color: fg,
      padding: "10px 14px",
      borderRadius: "var(--r-2)",
      fontSize: 13,
      border: "1px solid " + (tone === "warn" ? "var(--state-reprocess)" : tone === "danger" ? "var(--state-failed)" : "var(--line-1)"),
      borderColor: tone === "default" ? "var(--line-1)" : undefined,
    }}>
      <Icon name={icon} size={16} style={{ flex: "0 0 16px", marginTop: 1 }}/>
      <div style={{ flex: 1, color: "var(--ink-1)" }}>{children}</div>
    </div>
  );
};

// File extension to icon
const fileIcon = (name) => {
  if (/\.(mp3|m4a|wav|ogg)$/i.test(name)) return "audio";
  if (/\.(png|jpg|jpeg|gif|heic)$/i.test(name)) return "image";
  return "file";
};

// Make available
Object.assign(window, {
  StateBadge, Button, Card, Segmented, Topbar, StatTile, Avatar, Sidebar,
  InlineHint, fileIcon, STATE_LABELS,
});
