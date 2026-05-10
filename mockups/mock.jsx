// ========================================
// Mock data — 教師評語系統
// 假設教師: 陳芸老師 / 國中二年級 / 113 學年度
// ========================================

const TEACHER = {
  name: "陳芸",
  email: "yun.chen@dahu-jh.edu.tw",
  school: "大湖國中",
  grade: "二年級",
  consent_at: "2026-08-20T09:14:00",
  drive_root: "/我的雲端硬碟/教學資料",
  budget_monthly: 5.0,
  budget_used: 1.34,
};

// 學期
const SEMESTERS = [
  {
    label: "113-1 上學期",
    range: "2025/09 - 2026/01",
    students: 38,
    files: 1487,
    processed: 1487,
    cost: 1.04,
    state: "completed",
  },
  {
    label: "113-2 下學期",
    range: "2026/02 - 2026/06",
    students: 38,
    files: 1342,
    processed: 1163,
    cost: 0.82,
    state: "active",
  },
  {
    label: "112-2 下學期",
    range: "2025/02 - 2025/06",
    students: 36,
    files: 1289,
    processed: 1289,
    cost: 0.91,
    state: "archived",
  },
];

// 學生 — display_name 是教師看到的; pseudo_id 是送 LLM 的代號
const STUDENTS = [
  { pseudo: "S001", display: "子涵", real: "王子涵", note: "內向細膩,文采佳", files: 41, processed: 41, edited: 3, last: "2 小時前" },
  { pseudo: "S002", display: "宥嘉", real: "林宥嘉", note: "活潑,人緣好", files: 38, processed: 38, edited: 1, last: "今天 09:24" },
  { pseudo: "S003", display: "家瑋", real: "陳家瑋", note: "數理思維強", files: 44, processed: 44, edited: 5, last: "昨天" },
  { pseudo: "S004", display: "欣妍", real: "李欣妍", note: "閱讀量大", files: 39, processed: 36, edited: 0, last: "3 天前" },
  { pseudo: "S005", display: "育豪", real: "張育豪", note: "體育校隊,專注力提升中", files: 33, processed: 33, edited: 2, last: "今天 10:11" },
  { pseudo: "S006", display: "睿恩", real: "黃睿恩", note: "美術專長", files: 47, processed: 41, edited: 1, last: "1 小時前" },
  { pseudo: "S007", display: "柏翰", real: "吳柏翰", note: "默默用功,需要鼓勵", files: 36, processed: 36, edited: 0, last: "昨天" },
  { pseudo: "S008", display: "語彤", real: "蔡語彤", note: "領導才能突出", files: 42, processed: 42, edited: 4, last: "3 小時前" },
  { pseudo: "S009", display: "彥廷", real: "高彥廷", note: "數學競賽選手", files: 35, processed: 35, edited: 0, last: "5 天前" },
  { pseudo: "S010", display: "宜蓁", real: "周宜蓁", note: "音樂班學生", files: 40, processed: 40, edited: 2, last: "2 天前" },
  { pseudo: "S011", display: "丞勳", real: "謝丞勳", note: "近期需多關注", files: 28, processed: 24, edited: 0, last: "今天 08:30" },
  { pseudo: "S012", display: "若涵", real: "鄭若涵", note: "寫作獲獎", files: 45, processed: 45, edited: 6, last: "30 分鐘前" },
];

// PII mapping
const PII_MAPPING = [
  { ps: "S001", display: "子涵", real: "王子涵", type: "student_name", source: "auto" },
  { ps: "S002", display: "宥嘉", real: "林宥嘉", type: "student_name", source: "auto" },
  { ps: "S003", display: "家瑋", real: "陳家瑋", type: "student_name", source: "auto" },
  { ps: "S001", display: "—", real: "阿涵", type: "student_name", source: "manual" },
  { ps: "T001", display: "班導", real: "陳芸老師", type: "other_name", source: "auto" },
  { ps: "T002", display: "輔導", real: "李美玲", type: "other_name", source: "auto" },
  { ps: "P001", display: "—", real: "王先生", type: "parent_name", source: "auto" },
  { ps: "PH001", display: "—", real: "0912-345-678", type: "phone", source: "auto" },
  { ps: "EM001", display: "—", real: "wang.parent@gmail.com", type: "email", source: "auto" },
];

// 三類資料夾
const CATEGORIES = [
  { key: "learning", name: "學習紀錄", icon: "book", desc: "課堂作業、測驗、學習單" },
  { key: "interaction", name: "教師與學生互動紀錄", icon: "chat", desc: "晤談錄音、聯絡簿、輔導紀錄" },
  { key: "work", name: "作品成果", icon: "star", desc: "報告、創作、專題" },
];

// 子涵的素材檔案 (S001)
const FILES_ZIHAN = {
  learning: [
    { id: "f1", name: "週記-W12-反思閱讀的力量.docx", size: "24 KB", mtime: "2025-12-08", state: "edited", tier: "summary_cheap" },
    { id: "f2", name: "國文段考-第二次.pdf", size: "1.2 MB", mtime: "2025-11-18", state: "processed", tier: "summary_cheap" },
    { id: "f3", name: "閱讀心得-蛤蟆先生去看心理師.md", size: "8 KB", mtime: "2025-12-03", state: "processed", tier: "summary_cheap" },
    { id: "f4", name: "數學練習卷-小數除法.jpg", size: "2.4 MB", mtime: "2025-10-22", state: "processed", tier: "vision_cheap" },
    { id: "f5", name: "英文聽力筆記.txt", size: "3 KB", mtime: "2025-12-10", state: "processed", tier: "summary_cheap" },
    { id: "f6", name: "理化實驗報告-酸鹼指示劑.docx", size: "412 KB", mtime: "2025-11-30", state: "reprocess", tier: "summary_cheap" },
    { id: "f7", name: "社會科地圖作業.png", size: "1.8 MB", mtime: "2025-12-12", state: "processing", tier: "vision_cheap" },
    { id: "f8", name: "11月聯絡簿掃描.pdf", size: "5.1 MB", mtime: "2025-12-01", state: "pending", tier: "summary_cheap" },
  ],
  interaction: [
    { id: "f10", name: "10月晤談-關於閱讀偏好.m4a", size: "18.2 MB", mtime: "2025-10-15", state: "processed", tier: "audio_standard", duration: "12:34", speakers: 2 },
    { id: "f11", name: "11月家長日-家長對話.m4a", size: "32.1 MB", mtime: "2025-11-20", state: "edited", tier: "audio_standard", duration: "21:08", speakers: 3 },
    { id: "f12", name: "12月小組討論觀察.m4a", size: "24.8 MB", mtime: "2025-12-09", state: "processed", tier: "audio_standard", duration: "16:20", speakers: 4 },
    { id: "f13", name: "聯絡簿留言摘要.docx", size: "16 KB", mtime: "2025-12-05", state: "processed", tier: "summary_cheap" },
    { id: "f14", name: "12月觀察筆記-語音備忘.m4a", size: "8.4 MB", mtime: "2025-12-14", state: "failed", tier: "audio_standard", duration: "5:42", speakers: 1, fail: "音訊損毀" },
  ],
  work: [
    { id: "f20", name: "期末報告-台灣文學中的女性形象.pptx", size: "8.4 MB", mtime: "2025-12-15", state: "edited", tier: "summary_cheap" },
    { id: "f21", name: "英文短文創作-If I were a tree.pdf", size: "240 KB", mtime: "2025-11-25", state: "processed", tier: "summary_cheap" },
    { id: "f22", name: "美術作品-自畫像.jpg", size: "3.6 MB", mtime: "2025-12-12", state: "processed", tier: "vision_cheap" },
    { id: "f23", name: "理化專題-自製水質檢測.pdf", size: "1.9 MB", mtime: "2025-12-08", state: "processed", tier: "summary_cheap" },
    { id: "f24", name: "古典詩創作-冬日.docx", size: "12 KB", mtime: "2025-12-18", state: "processed", tier: "summary_cheap" },
  ],
};

// 子涵的 markdown 摘要範例
const SAMPLE_MD = `---
source: /113-1/王子涵/學習紀錄/閱讀心得-蛤蟆先生去看心理師.md
source_hash: a7f3c9...
processed_at: 2025-12-04T14:22:18
llm_tier: summary_cheap
llm_model: google/gemini-2.5-flash-lite
---

# 閱讀心得:蛤蟆先生去看心理師

## 摘要
S001 在這份心得中,以蛤蟆先生為鏡,反思自己「總是把別人的不滿先當成自己的錯」的傾向。
她特別注意到「兒童自我狀態」的概念,並嘗試用文字釐清自己在小組討論中沉默的原因。
全文共 612 字,結構從文本摘要 → 個人連結 → 反思行動建議三段推進。

## 重點內容
- 引用書中「父母自我狀態」與「成人自我狀態」三組概念,理解正確
- 將理論與自己「不敢在課堂發言」的經驗連結,具自我覺察
- 提出三項具體行動:每週至少舉手一次、用筆記方式練習表達、找人對談
- 結尾語氣堅定:「我想試著走出去」

## 原始引用
> 「我以前以為沉默就是沒有意見,但其實我是把『會被笑』的可能性放得太大了。」
> 「老師上次說我『心裡有想法但不愛說』,我那時候沒承認,現在我承認了。」`;

// 評語生成器 — 範例輸出
const SAMPLE_EVAL_SEED = `子涵這學期最大的成長是「願意把心裡話寫出來」。從週記、閱讀心得、晤談錄音中可以看到她從「沉默觀察」逐步走向「文字表達」,雖然口語仍偏內斂,但思辨能力與文字密度都明顯提升。希望她下學期能在課堂上嘗試發聲。`;

const SAMPLE_EVAL_OUTPUT = `子涵本學期最值得記錄的成長,是她開始願意把心裡的觀察化為文字。在《蛤蟆先生去看心理師》的閱讀心得中,她寫下「我以前以為沉默就是沒有意見,但其實我是把會被笑的可能性放得太大了」——這段反思讓我看見一位正在認識自己的學生。

學期間,她在週記與英文短文創作中持續展現細膩的觀察力與文字密度;〈If I were a tree〉用樹的視角寫下對時間的感受,結構成熟、語感清晰。十月晤談時她主動提到「想試著舉手一次」,這份意願在十一月小組討論的觀察中已能看到——雖仍多在傾聽,但發言時邏輯清楚、引用同學意見得體。

口語表達仍是她可以繼續鍛鍊的部分。建議下學期在「全班發表」之前,先以兩三人小組為練習場域,讓文字裡的思考慢慢長成口頭的聲音。她已經跨出了最重要的一步。`;

const SAMPLE_TRANSCRIPT = `---
source: /113-1/王子涵/教師與學生互動紀錄/10月晤談-關於閱讀偏好.m4a
duration_seconds: 754
speakers_detected: 2
llm_tier: audio_standard
---

# 互動紀錄:2025-10-15

## 講者標籤
- Speaker_1 → 子涵
- Speaker_2 → 老師

## 逐字稿

**[00:00:08] Speaker_2**:子涵,這次週記寫得很細,我想問你,你最近讀的書裡面,有沒有哪一本是你會想再讀一次的?

**[00:00:21] Speaker_1**:嗯⋯⋯就《蛤蟆先生去看心理師》。我覺得它寫的那個「兒童自我狀態」很⋯⋯很像我有時候的樣子。

**[00:00:38] Speaker_2**:可以說說看像在什麼時候嗎?

**[00:00:44] Speaker_1**:就⋯⋯小組討論的時候,我都不敢講話,因為我怕講錯,然後別人會笑我。可是後來我發現,我其實是先在心裡笑自己。

**[00:01:12] Speaker_2**:這個發現蠻重要的。你覺得寫下來之後,有比較好嗎?

**[00:01:18] Speaker_1**:有。寫下來會看清楚一點。
`;

// LLM tier config
const LLM_TIERS = [
  { key: "summary_cheap", name: "文件摘要", desc: "處理 .docx / .pdf / .txt", model: "google/gemini-2.5-flash-lite", price: "$0.0002 / 檔" },
  { key: "vision_cheap", name: "圖片 OCR", desc: "處理圖片、手寫掃描", model: "google/gemini-2.5-flash-lite", price: "$0.0005 / 檔" },
  { key: "audio_standard", name: "音訊轉錄", desc: "STT + 講者拆解", model: "google/gemini-2.5-flash-lite", price: "$0.011 / 小時" },
  { key: "evaluation_quality", name: "評語生成", desc: "整合素材撰寫評語", model: "google/gemini-2.5-flash-lite", price: "$0.0008 / 學生" },
];

const MODEL_OPTIONS = [
  "google/gemini-2.5-flash-lite",
  "google/gemini-2.5-flash",
  "google/gemini-2.5-pro",
  "anthropic/claude-haiku-4.5",
  "anthropic/claude-sonnet-4.5",
  "openai/gpt-5-mini",
];

// 批次處理:目前在進行中的範例
const BATCH_JOB = {
  semester: "113-2 下學期",
  status: "running",
  total: 1342,
  completed: 1163,
  failed: 7,
  skipped: 4,
  in_progress: 4,
  started: "2026-05-09T20:14:00",
  cost: 0.82,
  eta: "12 分鐘",
};

const BATCH_QUEUE_NOW = [
  { name: "S012/作品成果/期末創作-冬日詩集.docx", state: "processing", tier: "summary_cheap", elapsed: "8s" },
  { name: "S007/教師與學生互動紀錄/05月晤談.m4a", state: "processing", tier: "audio_standard", elapsed: "1m 22s" },
  { name: "S003/學習紀錄/數學週測卷.jpg", state: "processing", tier: "vision_cheap", elapsed: "4s" },
  { name: "S011/作品成果/英文短劇腳本.docx", state: "processing", tier: "summary_cheap", elapsed: "2s" },
];

const BATCH_REPROCESS = [
  { name: "S001/學習紀錄/理化實驗報告-酸鹼指示劑.docx", reason: "原檔已更新", edited: true },
  { name: "S008/作品成果/領導力營隊心得.docx", reason: "原檔已更新", edited: true },
  { name: "S005/教師與學生互動紀錄/03月家長對話.m4a", reason: "原檔已更新", edited: false },
];

// 圖示 — inline SVG
const Icon = ({ name, size = 16, ...rest }) => {
  const s = size;
  const stroke = "currentColor";
  const sw = 1.6;
  const paths = {
    book: <><path d="M4 4h6a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H4z"/><path d="M20 4h-6a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h7z"/></>,
    chat: <><path d="M21 12c0 4-4 7-9 7-1.4 0-2.7-.2-3.9-.6L3 20l1.4-3.5C3.5 15.3 3 13.7 3 12c0-4 4-7 9-7s9 3 9 7z"/></>,
    star: <><path d="M12 3l2.6 5.5 6 .9-4.3 4.3 1 6.1L12 17l-5.3 2.8 1-6.1L3.4 9.4l6-.9z"/></>,
    home: <><path d="M3 11.5L12 4l9 7.5"/><path d="M5 10v10h14V10"/></>,
    folder: <><path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></>,
    layers: <><path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/><path d="M3 18l9 5 9-5"/></>,
    edit: <><path d="M14 4l6 6-12 12H2v-6z"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3 1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8 1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></>,
    shield: <><path d="M12 3l8 3v6c0 5-3.5 8.5-8 9-4.5-.5-8-4-8-9V6z"/></>,
    play: <><path d="M6 4l14 8-14 8z"/></>,
    pause: <><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></>,
    check: <><path d="M5 12l5 5L20 7"/></>,
    x: <><path d="M6 6l12 12M18 6L6 18"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    arrowRight: <><path d="M5 12h14M13 6l6 6-6 6"/></>,
    arrowLeft: <><path d="M19 12H5M11 6l-6 6 6 6"/></>,
    download: <><path d="M12 4v12m0 0l-5-5m5 5l5-5"/><path d="M4 20h16"/></>,
    upload: <><path d="M12 20V8m0 0l-5 5m5-5l5 5"/><path d="M4 4h16"/></>,
    file: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/></>,
    audio: <><path d="M9 18V8l11-3v10"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="15" r="3"/></>,
    image: <><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/></>,
    sparkle: <><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/></>,
    chevronRight: <><path d="M9 6l6 6-6 6"/></>,
    chevronDown: <><path d="M6 9l6 6 6-6"/></>,
    search: <><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></>,
    google: <><path d="M21.6 12.2c0-.7-.1-1.4-.2-2H12v3.8h5.4c-.2 1.2-.9 2.3-2 3v2.5h3.2c1.9-1.7 3-4.3 3-7.3z" fill="#4285F4" stroke="none"/><path d="M12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.1H3.1v2.6C4.7 19.7 8.1 22 12 22z" fill="#34A853" stroke="none"/><path d="M6.4 14C6.2 13.4 6.1 12.7 6.1 12s.1-1.4.3-2V7.4H3.1C2.4 8.8 2 10.4 2 12s.4 3.2 1.1 4.6L6.4 14z" fill="#FBBC05" stroke="none"/><path d="M12 5.9c1.5 0 2.8.5 3.8 1.5l2.9-2.9C17 2.9 14.7 2 12 2 8.1 2 4.7 4.3 3.1 7.4L6.4 10c.8-2.3 3-4.1 5.6-4.1z" fill="#EA4335" stroke="none"/></>,
    drive: <><path d="M7.7 3l8.6 14.9h-5.6L2.1 3z" fill="#4285F4" stroke="none"/><path d="M16.3 3l-2.8 4.85L21.9 17.9 24 14.3 16.3 3z" fill="#FBBC05" stroke="none"/><path d="M11 14.6l-3.7 6.4h13.2L24 14.6z" fill="#34A853" stroke="none"/></>,
    user: <><circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-7 8-7s7 3 8 7"/></>,
    lock: <><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></>,
    bell: <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10 21a2 2 0 0 0 4 0"/></>,
    refresh: <><path d="M3 12a9 9 0 0 1 15.5-6.3L21 8"/><path d="M21 4v4h-4"/><path d="M21 12a9 9 0 0 1-15.5 6.3L3 16"/><path d="M3 20v-4h4"/></>,
    eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 8v.5M12 12v4"/></>,
    warning: <><path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/></>,
    dollar: <><path d="M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></>,
    cpu: <><rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/></>,
    list: <><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
  };
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" {...rest}>
      {paths[name] || null}
    </svg>
  );
};

// Make data + Icon globally available
Object.assign(window, {
  TEACHER, SEMESTERS, STUDENTS, PII_MAPPING, CATEGORIES, FILES_ZIHAN,
  SAMPLE_MD, SAMPLE_EVAL_SEED, SAMPLE_EVAL_OUTPUT, SAMPLE_TRANSCRIPT,
  LLM_TIERS, MODEL_OPTIONS, BATCH_JOB, BATCH_QUEUE_NOW, BATCH_REPROCESS,
  Icon,
});
