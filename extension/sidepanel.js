const state = {
  serverUrl: "",
  apiToken: "",
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
  openInboxLink: document.getElementById("open-inbox-link"),
  toggleSettingsBtn: document.getElementById("toggle-settings-btn"),
  settingsPanel: document.getElementById("settings-panel"),
  serverUrlInput: document.getElementById("server-url-input"),
  apiTokenInput: document.getElementById("api-token-input"),
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

function setStatus(el, text, isError = false) {
  el.textContent = text;
  el.classList.toggle("is-error", isError);
}

function showNotice(text, isError = false) {
  els.globalNotice.textContent = text;
  els.globalNotice.classList.toggle("is-error", isError);
  els.globalNotice.hidden = false;
}

function hideNotice() {
  els.globalNotice.hidden = true;
}

function setPendingTimestamp(seconds) {
  if (typeof seconds === "number" && Number.isFinite(seconds) && seconds >= 0) {
    state.pendingTimestamp = Math.floor(seconds);
    els.jotTsLabel.textContent = "Timestamp " + formatTimestamp(state.pendingTimestamp);
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
  const stored = await chrome.storage.local.get(["serverUrl", "apiToken"]);
  state.serverUrl = cleanServerUrl(stored.serverUrl || "http://localhost:8001");
  state.apiToken = (stored.apiToken || "").trim();
  els.serverUrlInput.value = state.serverUrl;
  els.apiTokenInput.value = state.apiToken;
  if (state.serverUrl) {
    els.openInboxLink.href = state.serverUrl + "/inbox";
    els.openInboxLink.hidden = false;
  }
  if (!hasConfig()) {
    els.settingsPanel.hidden = false;
  }
}

async function saveSettings() {
  const serverUrl = cleanServerUrl(els.serverUrlInput.value);
  const apiToken = els.apiTokenInput.value.trim();
  if (!isHttpUrl(serverUrl)) {
    setStatus(els.settingsStatus, "Enter a valid http(s) server URL.", true);
    return;
  }
  if (apiToken.length < 32) {
    setStatus(els.settingsStatus, "API token must be at least 32 characters.", true);
    return;
  }
  state.serverUrl = serverUrl;
  state.apiToken = apiToken;
  await chrome.storage.local.set({ serverUrl, apiToken });
  els.openInboxLink.href = serverUrl + "/inbox";
  els.openInboxLink.hidden = false;
  setStatus(els.settingsStatus, "Testing…");
  try {
    await apiRequest(
      "/api/v1/page-note?url=" + encodeURIComponent("https://example.com/")
    );
    setStatus(els.settingsStatus, "Connected!");
    els.settingsPanel.hidden = true;
    await refreshActiveTab();
  } catch (err) {
    setStatus(els.settingsStatus, "Connection failed: " + err.message, true);
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
      setStatus(els.notesStatus, "Saved");
    }
  } catch (err) {
    // Restore pending payload so a failed save can be retried unless superseded
    if (!state.notesDirty) {
      state.notesDirty = true;
      state.pendingSavePayload = payload;
    }
    if (state.rawUrl === payload.url || state.canonicalUrl === payload.url) {
      setStatus(els.notesStatus, "Save failed: " + err.message, true);
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
  setStatus(els.notesStatus, "Saving…");
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
    count > 0 ? `Add selected (${count})` : "Add selected";

  if (unpromotedIds.length > 0) {
    const allSelected = unpromotedIds.every((id) => state.selectedIds.has(id));
    els.toggleSelectAllBtn.hidden = false;
    els.toggleSelectAllBtn.textContent = allSelected ? "Select none" : "Select all";
  } else {
    els.toggleSelectAllBtn.hidden = true;
  }
}

function renderItems() {
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

    if (typeof item.timestamp_seconds === "number") {
      const tsBtn = document.createElement("button");
      tsBtn.type = "button";
      tsBtn.className = "sp-pill sp-pill-btn";
      tsBtn.textContent = formatTimestamp(item.timestamp_seconds);
      tsBtn.title = "Jump to timestamp (-2s)";
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
      link.textContent = "Added →";
      meta.appendChild(link);
    } else if (item.existing_entry_ids && item.existing_entry_ids.length) {
      item.existing_entry_ids.slice(0, 3).forEach((eid) => {
        const link = document.createElement("a");
        link.className = "sp-pill";
        link.href = `${state.serverUrl}/entry/${eid}`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = `In dictionary #${eid}`;
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
    lookupBtn.textContent = "Lookup";
    actions.appendChild(lookupBtn);

    if (!item.promoted_entry_id) {
      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "sp-link-btn";
      editBtn.textContent = "Edit";
      actions.appendChild(editBtn);

      editBtn.addEventListener("click", () => {
        toggleEditBox(li, item);
      });
    }

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "sp-link-btn";
    delBtn.textContent = "Delete";
    delBtn.addEventListener("click", async () => {
      try {
        await apiRequest(`/api/v1/page-note/items/${item.id}`, {
          method: "DELETE",
        });
        state.items = state.items.filter((it) => it.id !== item.id);
        renderItems();
      } catch (err) {
        setStatus(els.promoteStatus, "Delete failed: " + err.message, true);
      }
    });
    actions.appendChild(delBtn);

    li.appendChild(actions);

    lookupBtn.addEventListener("click", () => {
      toggleLookupBox(li, item.word);
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
  wordInput.placeholder = "Word or phrase";

  const ctxInput = document.createElement("input");
  ctxInput.type = "text";
  ctxInput.className = "sp-input";
  ctxInput.value = item.context || "";
  ctxInput.placeholder = "Context sentence";

  const defInput = document.createElement("textarea");
  defInput.className = "sp-textarea";
  defInput.rows = 3;
  defInput.value = item.definition_text || "";
  defInput.placeholder = "Optional definition (Markdown)";

  const row = document.createElement("div");
  row.className = "sp-row";
  row.style.marginTop = "6px";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "sp-btn sp-btn-primary";
  saveBtn.textContent = "Save";

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "sp-btn";
  cancelBtn.textContent = "Cancel";

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

async function renderLookupIntoBox(box, word, { includeDictLinks = false } = {}) {
  box.replaceChildren();
  box.textContent = "Looking up…";
  box.hidden = false;

  try {
    const data = await apiRequest(
      "/api/v1/lookup?word=" + encodeURIComponent(word)
    );
    box.replaceChildren();

    if (includeDictLinks) {
      const linksRow = createDictionaryLinksRow(word);
      linksRow.style.margin = "0 0 6px 0";
      box.appendChild(linksRow);
    }

    if (data.ipa) {
      const ipaEl = document.createElement("div");
      ipaEl.className = "sp-lookup-ipa";
      ipaEl.textContent = "/" + data.ipa + "/";
      box.appendChild(ipaEl);
    }

    if (data.existing_entries && data.existing_entries.length) {
      data.existing_entries.forEach((entry) => {
        const line = document.createElement("div");
        line.className = "sp-lookup-sense";
        const link = document.createElement("a");
        link.href = `${state.serverUrl}/entry/${entry.id}`;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = `Saved (${entry.visit_count} visits)`;
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
          syns.textContent = "Synonyms: " + sense.synonyms.slice(0, 8).join(", ");
          div.appendChild(syns);
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
      empty.textContent = "No thesaurus senses found.";
      box.appendChild(empty);
    }
  } catch (err) {
    box.replaceChildren();
    const errEl = document.createElement("div");
    errEl.className = "sp-status is-error";
    errEl.textContent = "Lookup failed: " + err.message;
    box.appendChild(errEl);
  }
}

async function toggleLookupBox(li, word) {
  const existing = li.querySelector(".sp-lookup-box");
  if (existing) {
    existing.remove();
    return;
  }
  const box = document.createElement("div");
  box.className = "sp-lookup-box";
  li.appendChild(box);
  await renderLookupIntoBox(box, word);
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
  setPendingTimestamp(null);
  setStatus(els.jotStatus, "");
  setStatus(els.promoteStatus, "");
  setStatus(els.notesStatus, "");

  els.pageTitle.textContent = state.title || "Untitled tab";
  els.pageUrl.textContent = state.rawUrl;

  if (!isHttpUrl(state.rawUrl)) {
    els.workspace.hidden = true;
    showNotice("Open a web page or YouTube video to take notes and capture vocabulary.");
    return;
  }

  if (!hasConfig()) {
    els.workspace.hidden = true;
    els.settingsPanel.hidden = false;
    showNotice("Configure your server URL and API token in Settings to connect.");
    return;
  }

  hideNotice();
  els.workspace.hidden = false;
  els.grabPageBtn.textContent = isYouTubeUrl(state.rawUrl)
    ? "Grab timestamp & caption"
    : "Grab selection";

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

    state.canonicalUrl = data.url || state.rawUrl;
    els.pageUrl.textContent = state.canonicalUrl;
    state.items = data.items || [];
    els.notesTextarea.value = data.notes_md || "";
    state.notesDirty = false;
    state.pendingSavePayload = null;
    renderItems();
  } catch (err) {
    if (err.name === "AbortError" || gen !== state.loadGeneration) return;
    showNotice("Could not load page notes: " + err.message, true);
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
    setStatus(els.jotStatus, "Full sentence grabbed from transcript");
  } else if (captured.source === "captions") {
    setStatus(els.jotStatus, "Full sentence grabbed from captions");
  } else if (captured.source === "overlay") {
    setStatus(
      els.jotStatus,
      "Partial caption only — open YouTube Transcript for full sentences"
    );
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
  els.settingsPanel.hidden = !els.settingsPanel.hidden;
});

els.saveSettingsBtn.addEventListener("click", saveSettings);
els.clearTsBtn.addEventListener("click", () => setPendingTimestamp(null));

els.jotLookupBtn.addEventListener("click", async () => {
  const word = els.jotWord.value.trim();
  if (!word) {
    setStatus(els.jotStatus, "Type a word first to look it up.", true);
    els.jotWord.focus();
    return;
  }
  if (!hasConfig()) return;
  setStatus(els.jotStatus, "");
  await renderLookupIntoBox(els.jotLookupBox, word, { includeDictLinks: true });
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
  setStatus(els.jotStatus, "Grabbing…");
  chrome.runtime.sendMessage(
    { type: "grabFromActiveTab", hintWord: els.jotWord.value.trim() },
    (resp) => {
      if (gen !== state.loadGeneration) return;
      if (chrome.runtime.lastError || !resp || !resp.ok) {
        setStatus(
          els.jotStatus,
          (resp && resp.error) || "Could not grab from page.",
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
  setStatus(els.jotStatus, "Saving…");
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
    els.jotLookupBox.hidden = true;
    els.jotLookupBox.replaceChildren();
    setPendingTimestamp(null);
    setStatus(els.jotStatus, "Saved");
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
  setStatus(els.promoteStatus, "Adding to dictionary…");
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
        const msg = r.error || r.status || "Failed";
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
    if (created) parts.push(`${created} added`);
    if (duplicates) parts.push(`${duplicates} linked to existing`);
    if (errorMessages.length) parts.push(errorMessages.join("; "));
    setStatus(els.promoteStatus, parts.join(" · ") || "Done", errorMessages.length > 0);
  } catch (err) {
    if (gen === state.loadGeneration) {
      setStatus(els.promoteStatus, "Promote failed: " + err.message, true);
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
