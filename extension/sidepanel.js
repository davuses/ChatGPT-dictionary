const STRINGS = {
  en: {
    inbox: "Inbox",
    settings: "Settings",
    loading_tab: "Loading tab…",
    untitled_tab: "Untitled tab",
    settings_title: "Connection settings",
    settings_server_url: "Server URL",
    settings_api_token: "API Token",
    settings_token_hint: "(stored locally only)",
    settings_token_placeholder: "Paste your API token from /account",
    settings_lang_label: "Language",
    settings_theme_label: "Theme",
    theme_auto: "Auto (System)",
    theme_auto_short: "Auto",
    theme_light: "Light",
    theme_dark: "Dark",
    lang_auto: "Auto (Browser)",
    save_test: "Save & test",
    close: "Close",
    show: "Show",
    hide: "Hide",
    get_token: "Get token ↗",
    update_available: "Extension v{version} is available",
    update_how: "How to update →",
    close_lookup: "Close lookup",
    select_item_aria: "Select {word}",
    confirm_delete: "Confirm?",
    def_added: "Definition added",
    quick_jot: "Quick jot",
    grab_from_page: "Grab from page",
    grab_selection: "Grab selection",
    grab_yt: "Grab timestamp & caption",
    jot_word_placeholder: "Word or phrase (e.g. finances)",
    jot_context_placeholder: "Context sentence (optional — Ctrl+Enter to save)",
    timestamp_label: "Timestamp {ts}",
    clear_ts: "Clear timestamp",
    jot_word: "Jot word",
    lookup: "Lookup",
    captured_words: "Captured words",
    select_all: "Select all",
    select_none: "Select none",
    add_selected: "Add selected",
    add_selected_n: "Add selected ({n})",
    items_empty: "No words jotted for this page yet.",
    scratchpad: "Page scratchpad",
    scratchpad_placeholder: "Freeform Markdown notes for this video or article…",
    play_pronunciation: "Play pronunciation",
    play_pronunciation_for: "Play pronunciation for {word}",
    jump_ts: "Jump to timestamp (-2s)",
    added_badge: "Added →",
    in_dict_badge: "In dictionary #{id}",
    edit: "Edit",
    delete: "Delete",
    save: "Save",
    cancel: "Cancel",
    edit_word_placeholder: "Word or phrase",
    edit_ctx_placeholder: "Context sentence",
    edit_def_placeholder: "Optional definition (Markdown)",
    looking_up: "Looking up…",
    saved_visits_one: "Saved ({n} visit)",
    saved_visits_many: "Saved ({n} visits)",
    synonyms_prefix: "Synonyms: ",
    use_sense: "+ Use",
    no_senses: "No thesaurus senses found.",
    lookup_failed: "Lookup failed: {err}",
    err_invalid_url: "Enter a valid http(s) server URL.",
    err_token_short: "API token must be at least 32 characters.",
    testing: "Testing…",
    connected: "Connected!",
    conn_failed: "Connection failed: {err}",
    saving: "Saving…",
    saved: "Saved",
    save_failed: "Save failed: {err}",
    delete_failed: "Delete failed: {err}",
    notice_open_page: "Open a web page or YouTube video to take notes and capture vocabulary.",
    notice_configure: "Configure your server URL and API token in Settings to connect.",
    notice_load_failed: "Could not load page notes: {err}",
    src_transcript: "Full sentence grabbed from transcript",
    src_captions: "Full sentence grabbed from captions",
    src_overlay: "Partial caption only — open YouTube Transcript for full sentences",
    type_word_first: "Type a word first to look it up.",
    grabbing: "Grabbing…",
    grab_failed: "Could not grab from page.",
    adding_to_dict: "Adding to dictionary…",
    promote_added: "{n} added",
    promote_linked: "{n} linked to existing",
    promote_done: "Done",
    promote_failed: "Promote failed: {err}",
    failed: "Failed",
  },
  "zh-CN": {
    inbox: "收件箱",
    settings: "设置",
    loading_tab: "正在加载标签页…",
    untitled_tab: "未命名标签页",
    settings_title: "连接设置",
    settings_server_url: "服务器地址",
    settings_api_token: "API 令牌",
    settings_token_hint: "（仅保存在本地）",
    settings_token_placeholder: "粘贴来自「账户」页面的 API 令牌",
    settings_lang_label: "界面语言",
    settings_theme_label: "明暗主题",
    theme_auto: "跟随系统",
    theme_auto_short: "自动",
    theme_light: "浅色",
    theme_dark: "深色",
    lang_auto: "跟随浏览器",
    save_test: "保存并测试",
    close: "关闭",
    show: "显示",
    hide: "隐藏",
    get_token: "获取令牌 ↗",
    update_available: "扩展有新版本 v{version}",
    update_how: "查看更新方法 →",
    close_lookup: "关闭查词",
    select_item_aria: "选中 {word}",
    confirm_delete: "确认删除？",
    def_added: "已添加到释义",
    quick_jot: "随手记词",
    grab_from_page: "从网页抓取",
    grab_selection: "抓取选中文本",
    grab_yt: "抓取时间点与字幕",
    jot_word_placeholder: "单词或短语（如 finances）",
    jot_context_placeholder: "语境原句（可选 — Ctrl+Enter 保存）",
    timestamp_label: "时间点 {ts}",
    clear_ts: "清除时间点",
    jot_word: "记下词条",
    lookup: "查词",
    captured_words: "本页已收集",
    select_all: "全选",
    select_none: "取消全选",
    add_selected: "入库选中项",
    add_selected_n: "入库选中项 ({n})",
    items_empty: "当前页面还没有记下生词。",
    scratchpad: "本页随手记",
    scratchpad_placeholder: "记录此视频或文章的自由 Markdown 笔记…",
    play_pronunciation: "播放发音",
    play_pronunciation_for: "播放 {word} 的发音",
    jump_ts: "跳转到时间点（提前 2 秒）",
    added_badge: "已入库 →",
    in_dict_badge: "词库已有 #{id}",
    edit: "编辑",
    delete: "删除",
    save: "保存",
    cancel: "取消",
    edit_word_placeholder: "单词或短语",
    edit_ctx_placeholder: "语境原句",
    edit_def_placeholder: "可选释义（支持 Markdown）",
    looking_up: "正在查询…",
    saved_visits_one: "词库已有（访问 {n} 次）",
    saved_visits_many: "词库已有（访问 {n} 次）",
    synonyms_prefix: "同义词：",
    use_sense: "+ 采用",
    no_senses: "未找到同义词释义。",
    lookup_failed: "查询失败：{err}",
    err_invalid_url: "请输入有效的 http(s) 服务器地址。",
    err_token_short: "API 令牌长度至少为 32 位。",
    testing: "正在测试连接…",
    connected: "已连接！",
    conn_failed: "连接失败：{err}",
    saving: "正在保存…",
    saved: "已保存",
    save_failed: "保存失败：{err}",
    delete_failed: "删除失败：{err}",
    notice_open_page: "打开任意网页或 YouTube 视频即可记笔记并收集生词。",
    notice_configure: "请先在「设置」中配置服务器地址和 API 令牌。",
    notice_load_failed: "无法加载本页笔记：{err}",
    src_transcript: "已从视频字幕列表抓取完整句子",
    src_captions: "已从字幕抓取完整句子",
    src_overlay: "仅抓取到片段字幕——展开 YouTube 字幕列表可抓取完整句子",
    type_word_first: "请先输入要查询的单词。",
    grabbing: "正在抓取…",
    grab_failed: "无法从当前页面抓取内容。",
    adding_to_dict: "正在加入词库…",
    promote_added: "新增 {n} 个",
    promote_linked: "关联已有 {n} 个",
    promote_done: "已完成",
    promote_failed: "入库失败：{err}",
    failed: "失败",
  },
};

const state = {
  serverUrl: "",
  apiToken: "",
  themePref: "auto",
  langPref: "auto",
  lang: "en",
  settingsOpen: false,
  workspaceShouldShow: false,
  noticeVisible: false,
  latestServerExtVersion: "",
  jotLookupWord: "",
  noticeKind: null,
  tabId: null,
  rawUrl: "",
  canonicalUrl: "",
  title: "",
  items: [],
  itemErrors: new Map(),
  selectedIds: new Set(),
  pendingTimestamp: null,
  notesDirty: false,
  notesSaveTimer: null,
  pendingSavePayload: null,
  loadAbortController: null,
  loadGeneration: 0,
};

const els = {
  brandLink: document.getElementById("brand-link"),
  openInboxLink: document.getElementById("open-inbox-link"),
  toggleSettingsBtn: document.getElementById("toggle-settings-btn"),
  closeSettingsBtn: document.getElementById("close-settings-btn"),
  extVersionBadge: document.getElementById("ext-version-badge"),
  pageBanner: document.getElementById("page-banner"),
  updateBanner: document.getElementById("update-banner"),
  updateBannerText: document.getElementById("update-banner-text"),
  updateBannerLink: document.getElementById("update-banner-link"),
  settingsPanel: document.getElementById("settings-panel"),
  serverUrlInput: document.getElementById("server-url-input"),
  apiTokenInput: document.getElementById("api-token-input"),
  toggleTokenVisBtn: document.getElementById("toggle-token-vis-btn"),
  getTokenLink: document.getElementById("get-token-link"),
  themeSegmented: document.getElementById("theme-segmented"),
  langSelect: document.getElementById("lang-select"),
  saveSettingsBtn: document.getElementById("save-settings-btn"),
  settingsStatus: document.getElementById("settings-status"),
  pageTitle: document.getElementById("page-title"),
  pageUrl: document.getElementById("page-url"),
  globalNotice: document.getElementById("global-notice"),
  workspace: document.getElementById("workspace"),
  grabPageBtn: document.getElementById("grab-page-btn"),
  jotForm: document.getElementById("jot-form"),
  jotWord: document.getElementById("jot-word"),
  jotContext: document.getElementById("jot-context"),
  jotSubmitBtn: document.getElementById("jot-submit-btn"),
  jotLookupBtn: document.getElementById("jot-lookup-btn"),
  jotLookupBox: document.getElementById("jot-lookup-box"),
  jotTsRow: document.getElementById("jot-ts-row"),
  jotTsLabel: document.getElementById("jot-ts-label"),
  clearTsBtn: document.getElementById("clear-ts-btn"),
  jotStatus: document.getElementById("jot-status"),
  itemsCount: document.getElementById("items-count"),
  itemsEmpty: document.getElementById("items-empty"),
  itemsList: document.getElementById("items-list"),
  toggleSelectAllBtn: document.getElementById("toggle-select-all-btn"),
  promoteSelectedBtn: document.getElementById("promote-selected-btn"),
  promoteStatus: document.getElementById("promote-status"),
  notesTextarea: document.getElementById("notes-textarea"),
  notesStatus: document.getElementById("notes-status"),
};

function resolveLang(pref) {
  if (pref === "en" || pref === "zh-CN") return pref;
  const uiLang =
    (typeof chrome !== "undefined" &&
      chrome.i18n &&
      typeof chrome.i18n.getUILanguage === "function" &&
      chrome.i18n.getUILanguage()) ||
    navigator.language ||
    "en";
  return uiLang.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
}

function t(key, vars) {
  const dict = STRINGS[state.lang] || STRINGS.en;
  let text = Object.prototype.hasOwnProperty.call(dict, key)
    ? dict[key]
    : STRINGS.en[key] || key;
  if (vars) {
    text = text.replace(/\{(\w+)\}/g, (match, name) =>
      Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match
    );
  }
  return text;
}

function applyTheme(pref) {
  const normalized = pref === "light" || pref === "dark" ? pref : "auto";
  state.themePref = normalized;
  if (normalized === "auto") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", normalized);
  }
  try {
    if (normalized === "auto") {
      localStorage.removeItem("glossbook_theme");
    } else {
      localStorage.setItem("glossbook_theme", normalized);
    }
  } catch (_) {}
  if (els.themeSegmented) {
    els.themeSegmented.querySelectorAll(".sp-seg-btn").forEach((btn) => {
      btn.setAttribute("aria-checked", String(btn.dataset.themeValue === normalized));
    });
  }
}

function getLocalExtensionVersion() {
  try {
    return (chrome.runtime && chrome.runtime.getManifest && chrome.runtime.getManifest().version) || "";
  } catch {
    return "";
  }
}

function isNewerVersion(remoteVer, localVer) {
  if (!remoteVer || !localVer) return false;
  const rParts = String(remoteVer).split(".").map((n) => parseInt(n, 10) || 0);
  const lParts = String(localVer).split(".").map((n) => parseInt(n, 10) || 0);
  const len = Math.max(rParts.length, lParts.length);
  for (let i = 0; i < len; i++) {
    const r = rParts[i] || 0;
    const l = lParts[i] || 0;
    if (r > l) return true;
    if (r < l) return false;
  }
  return false;
}

function syncUpdateBanner() {
  if (!els.updateBanner || !els.updateBannerText || !els.updateBannerLink) return;
  const localVer = getLocalExtensionVersion();
  if (
    state.latestServerExtVersion &&
    hasConfig() &&
    isNewerVersion(state.latestServerExtVersion, localVer)
  ) {
    els.updateBannerText.textContent = t("update_available", {
      version: state.latestServerExtVersion,
    });
    els.updateBannerLink.href = state.serverUrl + "/account#extension";
    els.updateBanner.hidden = false;
  } else {
    els.updateBanner.hidden = true;
  }
}

function syncViewVisibility() {
  els.settingsPanel.hidden = !state.settingsOpen;
  els.toggleSettingsBtn.classList.toggle("is-active", state.settingsOpen);
  els.toggleSettingsBtn.setAttribute("aria-expanded", String(state.settingsOpen));
  if (els.pageBanner) {
    els.pageBanner.hidden = state.settingsOpen;
  }
  els.workspace.hidden = state.settingsOpen || !state.workspaceShouldShow;
  els.globalNotice.hidden = state.settingsOpen || !state.noticeVisible;
}

function setSettingsOpen(open) {
  state.settingsOpen = Boolean(open);
  syncViewVisibility();
}

function syncServerLinks() {
  const configured = hasConfig();
  if (configured) {
    els.openInboxLink.href = state.serverUrl + "/inbox";
    els.openInboxLink.hidden = false;
    if (els.brandLink) {
      els.brandLink.href = state.serverUrl + "/";
      els.brandLink.removeAttribute("aria-disabled");
    }
  } else {
    els.openInboxLink.hidden = true;
    if (els.brandLink) {
      els.brandLink.href = "#";
      els.brandLink.setAttribute("aria-disabled", "true");
    }
  }
  syncGetTokenLink();
  syncUpdateBanner();
}

function syncGetTokenLink() {
  if (!els.getTokenLink) return;
  const raw = cleanServerUrl(els.serverUrlInput ? els.serverUrlInput.value : state.serverUrl);
  if (isHttpUrl(raw)) {
    els.getTokenLink.href = raw + "/account#extension";
    els.getTokenLink.hidden = false;
  } else {
    els.getTokenLink.hidden = true;
  }
}

function applyLanguage() {
  state.lang = resolveLang(state.langPref);
  document.documentElement.lang = state.lang;
  if (els.langSelect) {
    els.langSelect.value = state.langPref;
  }
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (key) el.textContent = t(key);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    if (key) el.placeholder = t(key);
  });
  if (els.toggleTokenVisBtn && els.apiTokenInput) {
    els.toggleTokenVisBtn.textContent =
      els.apiTokenInput.type === "text" ? t("hide") : t("show");
  }
  if (state.tabId !== null && !state.title) {
    els.pageTitle.textContent = t("untitled_tab");
  }
  if (isHttpUrl(state.rawUrl)) {
    els.grabPageBtn.textContent = isYouTubeUrl(state.rawUrl)
      ? t("grab_yt")
      : t("grab_selection");
  } else {
    els.grabPageBtn.textContent = t("grab_from_page");
  }
  setPendingTimestamp(state.pendingTimestamp);
  syncUpdateBanner();
  renderItems();
  if (els.workspace.hidden && state.noticeKind === "not_http") {
    showNotice(t("notice_open_page"), false, "not_http");
  } else if (els.workspace.hidden && state.noticeKind === "no_config") {
    showNotice(t("notice_configure"), false, "no_config");
  }
}

function formatTimestamp(seconds) {
  const sec = Math.max(0, Math.floor(seconds));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

function isHttpUrl(url) {
  return Boolean(url && /^https?:\/\//i.test(url));
}

function isYouTubeUrl(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    return host === "youtu.be" || host === "youtube.com" || host.endsWith(".youtube.com");
  } catch {
    return false;
  }
}

const DICTIONARY_LINKS = [
  {
    label: "Google",
    title: 'Search "define <word>" on Google',
    url: (w) => `https://www.google.com/search?q=${encodeURIComponent("define " + w)}`,
  },
  {
    label: "Oxford",
    title: "Search on Oxford Learner's Dictionaries",
    url: (w) =>
      `https://www.oxfordlearnersdictionaries.com/search/english/?q=${encodeURIComponent(w)}`,
  },
  {
    label: "Longman",
    title: "Search on Longman Dictionary",
    url: (w) =>
      `https://www.ldoceonline.com/search/english/direct/?q=${encodeURIComponent(w)}`,
  },
  {
    label: "MW",
    title: "Search on Merriam-Webster",
    url: (w) =>
      `https://www.merriam-webster.com/dictionary/${encodeURIComponent(w)}`,
  },
];

function createDictionaryLinksRow(word) {
  const row = document.createElement("div");
  row.className = "sp-dict-links";
  DICTIONARY_LINKS.forEach((site) => {
    const a = document.createElement("a");
    a.className = "sp-dict-link";
    a.href = site.url(word);
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.title = site.title;
    a.textContent = site.label;
    row.appendChild(a);
  });
  return row;
}

const SVG_NS = "http://www.w3.org/2000/svg";
let activeAudio = null;
let activeAudioButton = null;
let activeAudioToken = 0;

function stopPronunciation() {
  activeAudioToken += 1;
  if (activeAudio) {
    activeAudio.onended = null;
    activeAudio.onerror = null;
    activeAudio.pause();
    activeAudio = null;
  }
  if (activeAudioButton) {
    activeAudioButton.classList.remove("is-playing");
    activeAudioButton = null;
  }
  if ("speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
    } catch {
      // Ignore speechSynthesis cancellation errors
    }
  }
}

function buildPronunciationUrls(word) {
  const clean = (word || "").trim();
  if (!clean) return [];
  const urls = [];
  if (!/\s/.test(clean)) {
    const slug = encodeURIComponent(clean.toLowerCase());
    urls.push(`https://ssl.gstatic.com/dictionary/static/sounds/oxford/${slug}--_us_1.mp3`);
    urls.push(`https://ssl.gstatic.com/dictionary/static/sounds/oxford/x${slug}--_us_1.mp3`);
  }
  urls.push(
    `https://www.google.com/speech-api/v1/synthesize?text=${encodeURIComponent(
      clean
    )}&enc=mpeg&lang=en-us&speed=0.45&client=lr-language-tts&use_google_only_voices=1`
  );
  return urls;
}

function playPronunciation(word, button) {
  const clean = (word || "").trim();
  if (!clean || !button) return;
  if (activeAudioButton === button) {
    stopPronunciation();
    return;
  }
  stopPronunciation();

  const token = activeAudioToken;
  const urls = buildPronunciationUrls(clean);
  activeAudioButton = button;
  button.classList.add("is-playing");

  function finishIfCurrent() {
    if (token !== activeAudioToken) return;
    if (activeAudio) {
      activeAudio.onended = null;
      activeAudio.onerror = null;
      activeAudio = null;
    }
    if (activeAudioButton === button) {
      button.classList.remove("is-playing");
      activeAudioButton = null;
    }
  }

  function speakFallback() {
    if (token !== activeAudioToken) return;
    if (!("speechSynthesis" in window)) {
      finishIfCurrent();
      return;
    }
    try {
      const utter = new SpeechSynthesisUtterance(clean);
      utter.lang = "en-US";
      utter.onend = finishIfCurrent;
      utter.onerror = finishIfCurrent;
      window.speechSynthesis.speak(utter);
    } catch {
      finishIfCurrent();
    }
  }

  function tryUrl(index) {
    if (token !== activeAudioToken) return;
    if (index >= urls.length) {
      speakFallback();
      return;
    }
    const audio = new Audio();
    audio.referrerPolicy = "no-referrer";
    audio.preload = "auto";
    audio.src = urls[index];
    activeAudio = audio;

    let failed = false;
    function onFailure() {
      if (failed || token !== activeAudioToken) return;
      failed = true;
      audio.onended = null;
      audio.onerror = null;
      if (activeAudio === audio) activeAudio = null;
      tryUrl(index + 1);
    }

    audio.onended = finishIfCurrent;
    audio.onerror = onFailure;
    const playPromise = audio.play();
    if (playPromise && typeof playPromise.catch === "function") {
      playPromise.catch(onFailure);
    }
  }

  tryUrl(0);
}

function createSvgElement(tag, attrs) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    el.setAttribute(k, v);
  }
  return el;
}

function createAudioButton(word) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "sp-audio-btn";
  btn.title = t("play_pronunciation");
  btn.setAttribute("aria-label", t("play_pronunciation_for", { word }));

  const playSvg = createSvgElement("svg", {
    class: "icon-play",
    viewBox: "0 0 24 24",
    width: "16",
    height: "16",
    "aria-hidden": "true",
  });
  playSvg.appendChild(
    createSvgElement("circle", {
      cx: "12",
      cy: "12",
      r: "10",
      fill: "none",
      stroke: "currentColor",
      "stroke-width": "1.8",
    })
  );
  playSvg.appendChild(
    createSvgElement("polygon", {
      points: "10,8 16.5,12 10,16",
      fill: "currentColor",
    })
  );

  const pauseSvg = createSvgElement("svg", {
    class: "icon-pause",
    viewBox: "0 0 24 24",
    width: "16",
    height: "16",
    "aria-hidden": "true",
  });
  pauseSvg.appendChild(
    createSvgElement("circle", {
      cx: "12",
      cy: "12",
      r: "10",
      fill: "none",
      stroke: "currentColor",
      "stroke-width": "1.8",
    })
  );
  pauseSvg.appendChild(
    createSvgElement("rect", {
      x: "9",
      y: "8",
      width: "2.4",
      height: "8",
      rx: "0.6",
      fill: "currentColor",
    })
  );
  pauseSvg.appendChild(
    createSvgElement("rect", {
      x: "12.6",
      y: "8",
      width: "2.4",
      height: "8",
      rx: "0.6",
      fill: "currentColor",
    })
  );

  btn.appendChild(playSvg);
  btn.appendChild(pauseSvg);
  btn.addEventListener("click", () => playPronunciation(word, btn));
  return btn;
}

const statusTimers = new WeakMap();

function setStatus(el, text, isError = false, { autoClearMs = 0 } = {}) {
  if (statusTimers.has(el)) {
    clearTimeout(statusTimers.get(el));
    statusTimers.delete(el);
  }
  el.textContent = text;
  el.classList.toggle("is-error", isError);
  if (autoClearMs > 0 && text && !isError) {
    const timer = setTimeout(() => {
      if (el.textContent === text) {
        el.textContent = "";
      }
      statusTimers.delete(el);
    }, autoClearMs);
    statusTimers.set(el, timer);
  }
}

function showNotice(text, isError = false, kind = null) {
  state.noticeKind = kind;
  state.noticeVisible = true;
  els.globalNotice.textContent = text;
  els.globalNotice.classList.toggle("is-error", isError);
  syncViewVisibility();
}

function hideNotice() {
  state.noticeKind = null;
  state.noticeVisible = false;
  syncViewVisibility();
}

function setPendingTimestamp(seconds) {
  if (typeof seconds === "number" && Number.isFinite(seconds) && seconds >= 0) {
    state.pendingTimestamp = Math.floor(seconds);
    els.jotTsLabel.textContent = t("timestamp_label", {
      ts: formatTimestamp(state.pendingTimestamp),
    });
    els.jotTsRow.hidden = false;
  } else {
    state.pendingTimestamp = null;
    els.jotTsRow.hidden = true;
  }
}

function cleanServerUrl(url) {
  return (url || "").trim().replace(/\/+$/, "");
}

function hasConfig() {
  return Boolean(state.serverUrl && state.apiToken);
}

async function apiRequest(path, options = {}) {
  const headers = Object.assign(
    {
      Accept: "application/json",
      Authorization: "Bearer " + state.apiToken,
    },
    options.headers || {}
  );
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(
    state.serverUrl + path,
    Object.assign({ cache: "no-store" }, options, { headers })
  );
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const detail = (data && data.detail) || `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return data;
}

async function loadSettings() {
  const stored = await chrome.storage.local.get([
    "serverUrl",
    "apiToken",
    "langPref",
    "themePref",
  ]);
  state.serverUrl = cleanServerUrl(stored.serverUrl || "");
  state.apiToken = (stored.apiToken || "").trim();
  state.langPref =
    stored.langPref === "en" || stored.langPref === "zh-CN" ? stored.langPref : "auto";
  const themePref =
    stored.themePref === "light" || stored.themePref === "dark"
      ? stored.themePref
      : "auto";
  applyTheme(themePref);
  els.serverUrlInput.value = state.serverUrl;
  els.apiTokenInput.value = state.apiToken;
  if (els.extVersionBadge) {
    const ver = getLocalExtensionVersion();
    els.extVersionBadge.textContent = ver ? "v" + ver : "";
  }
  applyLanguage();
  syncServerLinks();
  if (!hasConfig()) {
    setSettingsOpen(true);
  }
}

async function saveSettings() {
  const serverUrl = cleanServerUrl(els.serverUrlInput.value);
  const apiToken = els.apiTokenInput.value.trim();
  const langPref = els.langSelect ? els.langSelect.value : state.langPref;
  state.langPref = langPref === "en" || langPref === "zh-CN" ? langPref : "auto";
  applyTheme(state.themePref);
  applyLanguage();
  if (!isHttpUrl(serverUrl)) {
    setStatus(els.settingsStatus, t("err_invalid_url"), true);
    return;
  }
  if (apiToken.length < 32) {
    setStatus(els.settingsStatus, t("err_token_short"), true);
    return;
  }
  state.serverUrl = serverUrl;
  state.apiToken = apiToken;
  await chrome.storage.local.set({
    serverUrl,
    apiToken,
    langPref: state.langPref,
    themePref: state.themePref,
  });
  syncServerLinks();
  setStatus(els.settingsStatus, t("testing"));
  try {
    const data = await apiRequest(
      "/api/v1/page-note?url=" + encodeURIComponent("https://example.com/")
    );
    if (data && data.latest_extension_version) {
      state.latestServerExtVersion = String(data.latest_extension_version);
      syncUpdateBanner();
    }
    setStatus(els.settingsStatus, t("connected"), false, { autoClearMs: 2500 });
    setSettingsOpen(false);
    await refreshActiveTab();
  } catch (err) {
    setStatus(els.settingsStatus, t("conn_failed", { err: err.message }), true);
  }
}

async function flushPendingNotesSave({ keepalive = false } = {}) {
  if (state.notesSaveTimer) {
    clearTimeout(state.notesSaveTimer);
    state.notesSaveTimer = null;
  }
  const payload = state.pendingSavePayload;
  if (!payload || !state.notesDirty || !hasConfig()) return;
  state.notesDirty = false;
  state.pendingSavePayload = null;
  try {
    await apiRequest("/api/v1/page-note", {
      method: "PUT",
      keepalive,
      body: JSON.stringify(payload),
    });
    if (state.rawUrl === payload.url || state.canonicalUrl === payload.url) {
      setStatus(els.notesStatus, t("saved"), false, { autoClearMs: 2500 });
    }
  } catch (err) {
    // Restore pending payload so a failed save can be retried unless superseded
    if (!state.notesDirty) {
      state.notesDirty = true;
      state.pendingSavePayload = payload;
    }
    if (state.rawUrl === payload.url || state.canonicalUrl === payload.url) {
      setStatus(els.notesStatus, t("save_failed", { err: err.message }), true);
    }
  }
}

function scheduleNotesSave() {
  if (!isHttpUrl(state.rawUrl) || !hasConfig()) return;
  state.notesDirty = true;
  state.pendingSavePayload = {
    url: state.canonicalUrl || state.rawUrl,
    title: state.title,
    notes_md: els.notesTextarea.value,
  };
  setStatus(els.notesStatus, t("saving"));
  if (state.notesSaveTimer) clearTimeout(state.notesSaveTimer);
  state.notesSaveTimer = setTimeout(() => {
    flushPendingNotesSave();
  }, 800);
}

function updatePromoteButton() {
  const unpromotedIds = state.items
    .filter((it) => !it.promoted_entry_id)
    .map((it) => it.id);
  const count = state.selectedIds.size;
  els.promoteSelectedBtn.hidden = count === 0;
  els.promoteSelectedBtn.textContent =
    count > 0 ? t("add_selected_n", { n: count }) : t("add_selected");

  if (unpromotedIds.length > 0) {
    const allSelected = unpromotedIds.every((id) => state.selectedIds.has(id));
    els.toggleSelectAllBtn.hidden = false;
    els.toggleSelectAllBtn.textContent = allSelected ? t("select_none") : t("select_all");
  } else {
    els.toggleSelectAllBtn.hidden = true;
  }
}

function renderItems() {
  if (activeAudioButton && els.itemsList.contains(activeAudioButton)) {
    stopPronunciation();
  }
  els.itemsList.replaceChildren();
  const items = state.items;
  const unpromotedCount = items.filter((it) => !it.promoted_entry_id).length;
  els.itemsCount.textContent = items.length ? `(${items.length})` : "";
  els.itemsEmpty.hidden = items.length > 0;

  // Prune selections for items that no longer exist or are already promoted
  const validSelectable = new Set(
    items.filter((it) => !it.promoted_entry_id).map((it) => it.id)
  );
  for (const id of Array.from(state.selectedIds)) {
    if (!validSelectable.has(id)) state.selectedIds.delete(id);
  }
  updatePromoteButton();

  items.forEach((item) => {
    const li = document.createElement("li");
    li.className = "sp-item" + (item.promoted_entry_id ? " is-promoted" : "");

    const top = document.createElement("div");
    top.className = "sp-item-top";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.disabled = Boolean(item.promoted_entry_id);
    checkbox.checked = state.selectedIds.has(item.id);
    checkbox.setAttribute("aria-label", t("select_item_aria", { word: item.word }));
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selectedIds.add(item.id);
      else state.selectedIds.delete(item.id);
      updatePromoteButton();
    });
    top.appendChild(checkbox);

    const wordEl = document.createElement("span");
    wordEl.className = "sp-item-word";
    wordEl.textContent = item.word;
    top.appendChild(wordEl);

    if (item.ipa) {
      const ipaEl = document.createElement("span");
      ipaEl.className = "sp-item-ipa";
      ipaEl.textContent = "/" + item.ipa + "/";
      top.appendChild(ipaEl);
    }

    top.appendChild(createAudioButton(item.word));

    if (typeof item.timestamp_seconds === "number") {
      const tsBtn = document.createElement("button");
      tsBtn.type = "button";
      tsBtn.className = "sp-pill sp-pill-btn";
      tsBtn.textContent = formatTimestamp(item.timestamp_seconds);
      tsBtn.title = t("jump_ts");
      tsBtn.addEventListener("click", () => {
        chrome.runtime.sendMessage({
          type: "seekYouTube",
          seconds: item.timestamp_seconds,
        });
      });
      top.appendChild(tsBtn);
    }

    li.appendChild(top);

    const meta = document.createElement("div");
    meta.className = "sp-item-meta";
    if (item.promoted_entry_id) {
      const link = document.createElement("a");
      link.className = "sp-pill";
      link.href = `${state.serverUrl}/entry/${item.promoted_entry_id}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = t("added_badge");
      meta.appendChild(link);
    } else if (item.existing_entry_ids && item.existing_entry_ids.length) {
      item.existing_entry_ids.slice(0, 3).forEach((eid) => {
        const link = document.createElement("a");
        link.className = "sp-pill";
        link.href = `${state.serverUrl}/entry/${eid}`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = t("in_dict_badge", { id: eid });
        meta.appendChild(link);
      });
    }
    if (meta.childNodes.length) li.appendChild(meta);

    if (item.context) {
      const ctx = document.createElement("p");
      ctx.className = "sp-item-context";
      ctx.textContent = item.context;
      li.appendChild(ctx);
    }
    if (item.definition_text) {
      const def = document.createElement("p");
      def.className = "sp-item-def";
      def.textContent = item.definition_text;
      li.appendChild(def);
    }

    const itemError = state.itemErrors.get(item.id);
    if (itemError) {
      const errP = document.createElement("p");
      errP.className = "sp-item-error";
      errP.textContent = itemError;
      li.appendChild(errP);
    }

    li.appendChild(createDictionaryLinksRow(item.word));

    const actions = document.createElement("div");
    actions.className = "sp-item-actions";

    const lookupBtn = document.createElement("button");
    lookupBtn.type = "button";
    lookupBtn.className = "sp-link-btn";
    lookupBtn.textContent = t("lookup");
    actions.appendChild(lookupBtn);

    if (!item.promoted_entry_id) {
      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "sp-link-btn";
      editBtn.textContent = t("edit");
      actions.appendChild(editBtn);

      editBtn.addEventListener("click", () => {
        toggleEditBox(li, item);
      });
    }

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "sp-link-btn sp-link-btn--danger";
    delBtn.textContent = t("delete");
    let deleteConfirmTimer = null;
    delBtn.addEventListener("click", async () => {
      if (!delBtn.classList.contains("is-confirming")) {
        delBtn.classList.add("is-confirming");
        delBtn.textContent = t("confirm_delete");
        deleteConfirmTimer = setTimeout(() => {
          delBtn.classList.remove("is-confirming");
          delBtn.textContent = t("delete");
        }, 4000);
        return;
      }
      if (deleteConfirmTimer) clearTimeout(deleteConfirmTimer);
      delBtn.disabled = true;
      try {
        await apiRequest(`/api/v1/page-note/items/${item.id}`, {
          method: "DELETE",
        });
        state.items = state.items.filter((it) => it.id !== item.id);
        renderItems();
      } catch (err) {
        delBtn.disabled = false;
        delBtn.classList.remove("is-confirming");
        delBtn.textContent = t("delete");
        setStatus(els.promoteStatus, t("delete_failed", { err: err.message }), true);
      }
    });
    actions.appendChild(delBtn);

    li.appendChild(actions);

    lookupBtn.addEventListener("click", () => {
      toggleLookupBox(li, item);
    });

    els.itemsList.appendChild(li);
  });

  // Keep subtle count if some are unpromoted
  if (unpromotedCount === 0 && items.length > 0) {
    els.promoteSelectedBtn.hidden = true;
  }
}

function toggleEditBox(li, item) {
  const existing = li.querySelector(".sp-edit-box");
  if (existing) {
    existing.remove();
    return;
  }
  const box = document.createElement("div");
  box.className = "sp-edit-box";

  const wordInput = document.createElement("input");
  wordInput.type = "text";
  wordInput.className = "sp-input";
  wordInput.value = item.word;
  wordInput.placeholder = t("edit_word_placeholder");

  const ctxInput = document.createElement("input");
  ctxInput.type = "text";
  ctxInput.className = "sp-input";
  ctxInput.value = item.context || "";
  ctxInput.placeholder = t("edit_ctx_placeholder");

  const defInput = document.createElement("textarea");
  defInput.className = "sp-textarea";
  defInput.rows = 3;
  defInput.value = item.definition_text || "";
  defInput.placeholder = t("edit_def_placeholder");

  const row = document.createElement("div");
  row.className = "sp-row";
  row.style.marginTop = "6px";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "sp-btn sp-btn-primary";
  saveBtn.textContent = t("save");

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "sp-btn";
  cancelBtn.textContent = t("cancel");

  const status = document.createElement("span");
  status.className = "sp-status";

  cancelBtn.addEventListener("click", () => box.remove());
  saveBtn.addEventListener("click", async () => {
    try {
      const resp = await apiRequest(`/api/v1/page-note/items/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          word: wordInput.value,
          context: ctxInput.value,
          definition_text: defInput.value,
        }),
      });
      const idx = state.items.findIndex((it) => it.id === item.id);
      if (idx >= 0 && resp.item) {
        state.items[idx] = resp.item;
      }
      renderItems();
    } catch (err) {
      setStatus(status, err.message, true);
    }
  });

  row.appendChild(saveBtn);
  row.appendChild(cancelBtn);
  row.appendChild(status);

  box.appendChild(wordInput);
  box.appendChild(ctxInput);
  box.appendChild(defInput);
  box.appendChild(row);
  li.appendChild(box);
}

async function renderLookupIntoBox(
  box,
  word,
  { includeDictLinks = false, onUseSense = null, onClose = null } = {}
) {
  box.replaceChildren();
  box.textContent = t("looking_up");
  box.hidden = false;

  try {
    const data = await apiRequest(
      "/api/v1/lookup?word=" + encodeURIComponent(word)
    );
    box.replaceChildren();

    const headRow = document.createElement("div");
    headRow.className = "sp-lookup-head";

    const ipaRow = document.createElement("div");
    ipaRow.className = "sp-lookup-ipa-row";
    if (data.ipa) {
      const ipaEl = document.createElement("span");
      ipaEl.className = "sp-lookup-ipa";
      ipaEl.textContent = "/" + data.ipa + "/";
      ipaRow.appendChild(ipaEl);
    }
    ipaRow.appendChild(createAudioButton(word));
    headRow.appendChild(ipaRow);

    if (typeof onClose === "function") {
      const closeBtn = document.createElement("button");
      closeBtn.type = "button";
      closeBtn.className = "sp-lookup-close-btn";
      closeBtn.setAttribute("aria-label", t("close_lookup"));
      closeBtn.title = t("close_lookup");
      closeBtn.textContent = "×";
      closeBtn.addEventListener("click", onClose);
      headRow.appendChild(closeBtn);
    }
    box.appendChild(headRow);

    if (includeDictLinks) {
      const linksRow = createDictionaryLinksRow(word);
      linksRow.style.margin = "0 0 6px 0";
      box.appendChild(linksRow);
    }

    if (data.existing_entries && data.existing_entries.length) {
      data.existing_entries.forEach((entry) => {
        const line = document.createElement("div");
        line.className = "sp-lookup-sense";
        const link = document.createElement("a");
        link.href = `${state.serverUrl}/entry/${entry.id}`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = t(
          entry.visit_count === 1 ? "saved_visits_one" : "saved_visits_many",
          { n: entry.visit_count }
        );
        line.appendChild(link);
        if (entry.context) {
          const span = document.createElement("span");
          span.textContent = " — " + entry.context;
          line.appendChild(span);
        }
        box.appendChild(line);
      });
    }

    if (data.senses && data.senses.length) {
      data.senses.slice(0, 4).forEach((sense) => {
        const div = document.createElement("div");
        div.className = "sp-lookup-sense";

        if (sense.part_of_speech) {
          const pos = document.createElement("span");
          pos.className = "sp-lookup-pos";
          pos.textContent = sense.part_of_speech;
          div.appendChild(pos);
        }
        if (sense.meaning) {
          const meaning = document.createElement("span");
          meaning.textContent = sense.meaning;
          div.appendChild(meaning);
        }
        if (sense.synonyms && sense.synonyms.length) {
          const syns = document.createElement("div");
          syns.className = "sp-lookup-syns";
          syns.textContent = t("synonyms_prefix") + sense.synonyms.slice(0, 8).join(", ");
          div.appendChild(syns);
        }
        if (typeof onUseSense === "function" && sense.meaning) {
          const useBtn = document.createElement("button");
          useBtn.type = "button";
          useBtn.className = "sp-pill sp-pill-btn sp-use-btn";
          useBtn.textContent = t("use_sense");
          useBtn.addEventListener("click", () => {
            useBtn.disabled = true;
            const formatted = sense.part_of_speech
              ? `(${sense.part_of_speech}) ${sense.meaning}`
              : sense.meaning;
            Promise.resolve(onUseSense(formatted)).finally(() => {
              useBtn.disabled = false;
            });
          });
          div.appendChild(useBtn);
        }
        box.appendChild(div);
      });
    } else if (data.thesaurus_error) {
      const errEl = document.createElement("div");
      errEl.className = "sp-status is-error";
      errEl.textContent = data.thesaurus_error;
      box.appendChild(errEl);
    } else if (!data.existing_entries || !data.existing_entries.length) {
      const empty = document.createElement("div");
      empty.className = "sp-status";
      empty.textContent = t("no_senses");
      box.appendChild(empty);
    }
  } catch (err) {
    box.replaceChildren();
    const errEl = document.createElement("div");
    errEl.className = "sp-status is-error";
    errEl.textContent = t("lookup_failed", { err: err.message });
    box.appendChild(errEl);
  }
}

async function toggleLookupBox(li, item) {
  const existing = li.querySelector(".sp-lookup-box");
  if (existing) {
    existing.remove();
    return;
  }
  const box = document.createElement("div");
  box.className = "sp-lookup-box";
  li.appendChild(box);
  const onUseSense = !item.promoted_entry_id
    ? async (formattedSense) => {
        const prev = (item.definition_text || "").trim();
        const nextDef = prev ? `${prev}\n${formattedSense}` : formattedSense;
        try {
          const resp = await apiRequest(`/api/v1/page-note/items/${item.id}`, {
            method: "PATCH",
            body: JSON.stringify({
              word: item.word,
              context: item.context || "",
              definition_text: nextDef,
            }),
          });
          const idx = state.items.findIndex((it) => it.id === item.id);
          if (idx >= 0 && resp.item) {
            state.items[idx] = resp.item;
          }
          renderItems();
          setStatus(els.promoteStatus, t("def_added"), false, { autoClearMs: 2800 });
        } catch (err) {
          setStatus(els.promoteStatus, t("save_failed", { err: err.message }), true);
        }
      }
    : null;
  await renderLookupIntoBox(box, item.word, {
    onUseSense,
    onClose: () => box.remove(),
  });
}

function samePageUrl(urlA, urlB) {
  if (!urlA || !urlB) return false;
  if (urlA === urlB) return true;
  try {
    const a = new URL(urlA);
    const b = new URL(urlB);
    if (isYouTubeUrl(urlA) && isYouTubeUrl(urlB)) {
      const vid = (u) => {
        if (u.hostname.toLowerCase() === "youtu.be") {
          return u.pathname.split("/").filter(Boolean)[0] || "";
        }
        if (u.searchParams.get("v")) return u.searchParams.get("v");
        const parts = u.pathname.split("/").filter(Boolean);
        return parts.length >= 2 && ["shorts", "live", "embed"].includes(parts[0])
          ? parts[1]
          : "";
      };
      const va = vid(a);
      const vb = vid(b);
      if (va && vb) return va === vb;
    }
    return a.origin === b.origin && a.pathname === b.pathname;
  } catch {
    return false;
  }
}

async function loadPageForTab(tab) {
  stopPronunciation();
  await flushPendingNotesSave();

  const gen = ++state.loadGeneration;
  if (state.loadAbortController) {
    state.loadAbortController.abort();
  }

  state.tabId = tab ? tab.id : null;
  state.rawUrl = tab && tab.url ? tab.url : "";
  state.title = tab && tab.title ? tab.title : "";
  state.canonicalUrl = "";
  state.items = [];
  state.itemErrors.clear();
  state.selectedIds.clear();
  els.jotWord.value = "";
  els.jotContext.value = "";
  els.jotLookupBox.hidden = true;
  els.jotLookupBox.replaceChildren();
  state.jotLookupWord = "";
  setPendingTimestamp(null);
  setStatus(els.jotStatus, "");
  setStatus(els.promoteStatus, "");
  setStatus(els.notesStatus, "");

  els.pageTitle.textContent = state.title || t("untitled_tab");
  els.pageUrl.textContent = state.rawUrl;

  if (!isHttpUrl(state.rawUrl)) {
    state.workspaceShouldShow = false;
    showNotice(t("notice_open_page"), false, "not_http");
    return;
  }

  if (!hasConfig()) {
    state.workspaceShouldShow = false;
    setSettingsOpen(true);
    showNotice(t("notice_configure"), false, "no_config");
    return;
  }

  state.workspaceShouldShow = true;
  hideNotice();
  syncViewVisibility();
  els.grabPageBtn.textContent = isYouTubeUrl(state.rawUrl)
    ? t("grab_yt")
    : t("grab_selection");

  const controller = new AbortController();
  state.loadAbortController = controller;

  try {
    const query =
      "/api/v1/page-note?url=" +
      encodeURIComponent(state.rawUrl) +
      "&title=" +
      encodeURIComponent(state.title);
    const data = await apiRequest(query, { signal: controller.signal });
    if (controller.signal.aborted || gen !== state.loadGeneration) return;

    if (data && data.latest_extension_version) {
      state.latestServerExtVersion = String(data.latest_extension_version);
      syncUpdateBanner();
    }
    state.canonicalUrl = data.url || state.rawUrl;
    els.pageUrl.textContent = state.canonicalUrl;
    state.items = data.items || [];
    els.notesTextarea.value = data.notes_md || "";
    state.notesDirty = false;
    state.pendingSavePayload = null;
    renderItems();
  } catch (err) {
    if (err.name === "AbortError" || gen !== state.loadGeneration) return;
    showNotice(t("notice_load_failed", { err: err.message }), true);
  }
}

async function refreshActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  await loadPageForTab(tab || null);
}

function applyCapturedPayload(captured, { verifyTabUrl = false } = {}) {
  if (!captured) return;
  if (
    verifyTabUrl &&
    captured.url &&
    state.rawUrl &&
    !samePageUrl(captured.url, state.rawUrl)
  ) {
    return;
  }
  if (captured.word) els.jotWord.value = captured.word;
  if (captured.context) els.jotContext.value = captured.context;
  setPendingTimestamp(captured.timestampSeconds);
  if (captured.source === "transcript") {
    setStatus(els.jotStatus, t("src_transcript"));
  } else if (captured.source === "captions") {
    setStatus(els.jotStatus, t("src_captions"));
  } else if (captured.source === "overlay") {
    setStatus(els.jotStatus, t("src_overlay"));
  }
  if (!els.jotWord.value) {
    els.jotWord.focus();
  } else {
    els.jotContext.focus();
  }
}

async function consumePendingCapture() {
  const stored = await chrome.storage.session.get("pendingCapture");
  if (!stored.pendingCapture) return;
  const captured = stored.pendingCapture;
  await chrome.storage.session.remove("pendingCapture");
  applyCapturedPayload(captured, { verifyTabUrl: true });
}

els.toggleSettingsBtn.addEventListener("click", () => {
  setSettingsOpen(els.settingsPanel.hidden);
});

if (els.closeSettingsBtn) {
  els.closeSettingsBtn.addEventListener("click", () => setSettingsOpen(false));
}

if (els.serverUrlInput) {
  els.serverUrlInput.addEventListener("input", syncGetTokenLink);
}

if (els.toggleTokenVisBtn && els.apiTokenInput) {
  els.toggleTokenVisBtn.addEventListener("click", () => {
    const showing = els.apiTokenInput.type === "text";
    els.apiTokenInput.type = showing ? "password" : "text";
    els.toggleTokenVisBtn.textContent = showing ? t("show") : t("hide");
  });
}

if (els.themeSegmented) {
  els.themeSegmented.addEventListener("click", (event) => {
    const btn = event.target.closest(".sp-seg-btn");
    if (!btn) return;
    applyTheme(btn.dataset.themeValue || "auto");
    chrome.storage.local.set({ themePref: state.themePref });
  });
}

if (els.langSelect) {
  els.langSelect.addEventListener("change", () => {
    const nextPref = els.langSelect.value;
    state.langPref = nextPref === "en" || nextPref === "zh-CN" ? nextPref : "auto";
    chrome.storage.local.set({ langPref: state.langPref });
    applyLanguage();
  });
}

els.saveSettingsBtn.addEventListener("click", saveSettings);
els.clearTsBtn.addEventListener("click", () => setPendingTimestamp(null));

function closeJotLookupBox() {
  els.jotLookupBox.hidden = true;
  els.jotLookupBox.replaceChildren();
  state.jotLookupWord = "";
}

els.jotLookupBtn.addEventListener("click", async () => {
  const word = els.jotWord.value.trim();
  if (!word) {
    setStatus(els.jotStatus, t("type_word_first"), true);
    els.jotWord.focus();
    return;
  }
  if (!hasConfig()) return;
  if (!els.jotLookupBox.hidden && state.jotLookupWord.toLowerCase() === word.toLowerCase()) {
    closeJotLookupBox();
    return;
  }
  state.jotLookupWord = word;
  setStatus(els.jotStatus, "");
  await renderLookupIntoBox(els.jotLookupBox, word, {
    includeDictLinks: true,
    onClose: closeJotLookupBox,
  });
});

els.jotContext.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    els.jotForm.requestSubmit();
  }
});

els.toggleSelectAllBtn.addEventListener("click", () => {
  const unpromotedIds = state.items
    .filter((it) => !it.promoted_entry_id)
    .map((it) => it.id);
  const allSelected = unpromotedIds.every((id) => state.selectedIds.has(id));
  if (allSelected) {
    state.selectedIds.clear();
  } else {
    unpromotedIds.forEach((id) => state.selectedIds.add(id));
  }
  renderItems();
});

els.grabPageBtn.addEventListener("click", () => {
  const gen = state.loadGeneration;
  setStatus(els.jotStatus, t("grabbing"));
  chrome.runtime.sendMessage(
    { type: "grabFromActiveTab", hintWord: els.jotWord.value.trim() },
    (resp) => {
      if (gen !== state.loadGeneration) return;
      if (chrome.runtime.lastError || !resp || !resp.ok) {
        setStatus(
          els.jotStatus,
          (resp && resp.error) || t("grab_failed"),
          true
        );
        return;
      }
      setStatus(els.jotStatus, "");
      applyCapturedPayload(resp.data, { verifyTabUrl: true });
    }
  );
});

els.jotForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!hasConfig() || !isHttpUrl(state.rawUrl) || els.jotSubmitBtn.disabled) return;
  const word = els.jotWord.value.trim();
  if (!word) return;

  const gen = state.loadGeneration;
  const targetUrl = state.canonicalUrl || state.rawUrl;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const freshTitle = (tab && tab.title) || state.title;
  if (gen === state.loadGeneration) state.title = freshTitle;

  els.jotSubmitBtn.disabled = true;
  setStatus(els.jotStatus, t("saving"));
  try {
    const resp = await apiRequest("/api/v1/page-note/items", {
      method: "POST",
      body: JSON.stringify({
        url: targetUrl,
        title: freshTitle,
        word,
        context: els.jotContext.value.trim(),
        timestamp_seconds: state.pendingTimestamp,
      }),
    });
    if (gen !== state.loadGeneration) return;
    if (resp.item) {
      state.items.push(resp.item);
      state.selectedIds.add(resp.item.id);
      renderItems();
    }
    els.jotWord.value = "";
    els.jotContext.value = "";
    closeJotLookupBox();
    setPendingTimestamp(null);
    setStatus(els.jotStatus, t("saved"), false, { autoClearMs: 2500 });
    els.jotWord.focus();
  } catch (err) {
    if (gen === state.loadGeneration) {
      setStatus(els.jotStatus, err.message, true);
    }
  } finally {
    els.jotSubmitBtn.disabled = false;
  }
});

els.promoteSelectedBtn.addEventListener("click", async () => {
  const itemIds = Array.from(state.selectedIds);
  if (!itemIds.length || els.promoteSelectedBtn.disabled) return;
  const gen = state.loadGeneration;
  els.promoteSelectedBtn.disabled = true;
  setStatus(els.promoteStatus, t("adding_to_dict"));
  try {
    const resp = await apiRequest("/api/v1/page-note/promote", {
      method: "POST",
      body: JSON.stringify({ item_ids: itemIds }),
    });
    if (gen !== state.loadGeneration) return;
    const byId = new Map((resp.results || []).map((r) => [r.item_id, r]));
    let created = 0;
    let duplicates = 0;
    const errorMessages = [];
    state.items = state.items.map((item) => {
      const r = byId.get(item.id);
      if (!r) return item;
      if (r.status === "created") {
        created += 1;
        state.itemErrors.delete(item.id);
      } else if (r.status === "duplicate" || r.status === "already_promoted") {
        duplicates += 1;
        state.itemErrors.delete(item.id);
      } else {
        const msg = r.error || r.status || t("failed");
        state.itemErrors.set(item.id, msg);
        errorMessages.push(`${item.word}: ${msg}`);
      }
      if (r.entry_id) {
        return Object.assign({}, item, { promoted_entry_id: r.entry_id });
      }
      return item;
    });
    state.selectedIds.clear();
    renderItems();
    const parts = [];
    if (created) parts.push(t("promote_added", { n: created }));
    if (duplicates) parts.push(t("promote_linked", { n: duplicates }));
    if (errorMessages.length) parts.push(errorMessages.join("; "));
    setStatus(els.promoteStatus, parts.join(" · ") || t("promote_done"), errorMessages.length > 0);
  } catch (err) {
    if (gen === state.loadGeneration) {
      setStatus(els.promoteStatus, t("promote_failed", { err: err.message }), true);
    }
  } finally {
    els.promoteSelectedBtn.disabled = false;
  }
});

els.notesTextarea.addEventListener("input", scheduleNotesSave);

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    flushPendingNotesSave({ keepalive: true });
  }
});

chrome.tabs.onActivated.addListener(() => {
  refreshActiveTab();
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!tab.active) return;
  if (changeInfo.url) {
    loadPageForTab(tab);
  } else if (changeInfo.title && tabId === state.tabId) {
    state.title = changeInfo.title;
    els.pageTitle.textContent = changeInfo.title;
  }
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "session" && changes.pendingCapture && changes.pendingCapture.newValue) {
    consumePendingCapture();
  }
});

(async function init() {
  await loadSettings();
  await refreshActiveTab();
  await consumePendingCapture();
})();
