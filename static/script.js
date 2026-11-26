let _i18nCache = null;

function _getI18nMap() {
  if (_i18nCache !== null) return _i18nCache;
  const el = document.getElementById("i18n-data");
  if (!el) {
    _i18nCache = {};
    return _i18nCache;
  }
  try {
    _i18nCache = JSON.parse(el.textContent || "{}") || {};
  } catch (_) {
    _i18nCache = {};
  }
  return _i18nCache;
}

function uiText(key, vars = {}, fallback = "") {
  const map = _getI18nMap();
  let template = Object.prototype.hasOwnProperty.call(map, key)
    ? map[key]
    : fallback || key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      template = template.replaceAll("{" + k + "}", String(v));
    }
  }
  return template;
}

function getThemePreference() {
  try {
    const saved = localStorage.getItem("glossbook_theme");
    return saved === "light" || saved === "dark" ? saved : "auto";
  } catch (_) {
    return "auto";
  }
}

function applyThemePreference(pref) {
  const normalized = pref === "light" || pref === "dark" ? pref : "auto";
  try {
    if (normalized === "auto") {
      localStorage.removeItem("glossbook_theme");
    } else {
      localStorage.setItem("glossbook_theme", normalized);
    }
  } catch (_) {}

  if (normalized === "auto") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", normalized);
  }

  const isDark =
    normalized === "dark" ||
    (normalized === "auto" &&
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  const meta = document.getElementById("theme-color-meta");
  if (meta) meta.setAttribute("content", isDark ? "#0A0D0C" : "#F6F6F4");

  const labelKey =
    normalized === "dark"
      ? "theme_dark"
      : normalized === "light"
      ? "theme_light"
      : "theme_auto";
  const fallback =
    normalized === "dark"
      ? "Theme: Dark"
      : normalized === "light"
      ? "Theme: Light"
      : "Theme: Auto";
  const label = uiText(labelKey, null, fallback);
  document.querySelectorAll(".theme-toggle-btn").forEach((btn) => {
    btn.textContent = label;
  });
  document.querySelectorAll(".theme-seg-btn").forEach((btn) => {
    const active = btn.dataset.themeValue === normalized;
    btn.setAttribute("aria-checked", String(active));
    btn.classList.toggle("is-active", active);
  });
}

function setRailCollapsed(collapsed) {
  if (collapsed) {
    document.documentElement.setAttribute("data-rail", "collapsed");
    try {
      localStorage.setItem("glossbook_rail", "collapsed");
    } catch (_) {}
  } else {
    document.documentElement.removeAttribute("data-rail");
    try {
      localStorage.removeItem("glossbook_rail");
    } catch (_) {}
  }
}

function initRailAndDrawer() {
  const rail = document.getElementById("app-rail");
  if (!rail) return;
  const collapseBtn = document.getElementById("rail-collapse-btn");
  const expandBtn = document.getElementById("rail-expand-btn");
  const moreBtn = document.getElementById("mobile-more-btn");
  const backdrop = document.getElementById("app-rail-backdrop");

  function isMobileViewport() {
    return window.matchMedia && window.matchMedia("(max-width: 959px)").matches;
  }

  function setDrawerOpen(open) {
    rail.classList.toggle("is-drawer-open", open);
    if (backdrop) backdrop.hidden = !open;
    if (moreBtn) moreBtn.setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("drawer-open", open);
    if (!open && moreBtn && rail.contains(document.activeElement)) {
      moreBtn.focus();
    }
  }

  if (collapseBtn) {
    collapseBtn.addEventListener("click", () => {
      if (isMobileViewport()) {
        setDrawerOpen(false);
      } else {
        setRailCollapsed(true);
      }
    });
  }
  if (expandBtn) {
    expandBtn.addEventListener("click", () => {
      if (isMobileViewport()) {
        setDrawerOpen(true);
      } else {
        setRailCollapsed(false);
      }
    });
  }
  if (moreBtn) {
    moreBtn.addEventListener("click", () => {
      setDrawerOpen(!rail.classList.contains("is-drawer-open"));
    });
  }
  if (backdrop) {
    backdrop.addEventListener("click", () => setDrawerOpen(false));
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && rail.classList.contains("is-drawer-open")) {
      setDrawerOpen(false);
      return;
    }
    if (event.key === "[" && !shouldIgnoreShortcut(event) && !isMobileViewport()) {
      event.preventDefault();
      const collapsed = document.documentElement.getAttribute("data-rail") === "collapsed";
      setRailCollapsed(!collapsed);
    }
  });
}

function showToast(message, { type = "info", duration = 2600 } = {}) {
  const region = document.getElementById("toast-region");
  if (!region || !message) return;
  const el = document.createElement("div");
  el.className = "toast" + (type === "error" ? " toast--error" : "");
  el.textContent = message;
  region.appendChild(el);
  setTimeout(() => {
    el.remove();
  }, duration);
}

function confirmDialog(message, { danger = false, title, okText, cancelText } = {}) {
  const dialog = document.getElementById("confirm-dialog");
  if (!dialog || typeof dialog.showModal !== "function") {
    return Promise.resolve(window.confirm(message));
  }
  const titleEl = document.getElementById("confirm-dialog-title");
  const msgEl = document.getElementById("confirm-dialog-message");
  const okBtn = document.getElementById("confirm-dialog-ok");
  const cancelBtn = document.getElementById("confirm-dialog-cancel");

  titleEl.textContent = title || uiText("confirm_title", null, "Please confirm");
  msgEl.textContent = message;
  okBtn.textContent = okText || uiText("confirm_ok", null, "Confirm");
  cancelBtn.textContent = cancelText || uiText("confirm_cancel", null, "Cancel");
  okBtn.classList.toggle("button-danger", Boolean(danger));
  okBtn.classList.toggle("button-primary", !danger);

  return new Promise((resolve) => {
    let settled = false;
    function finish(result) {
      if (settled) return;
      settled = true;
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      dialog.removeEventListener("cancel", onCancel);
      if (dialog.open) dialog.close();
      resolve(result);
    }
    function onOk() {
      finish(true);
    }
    function onCancel() {
      finish(false);
    }
    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
    dialog.addEventListener("cancel", onCancel);
    dialog.showModal();
  });
}

function shouldIgnoreShortcut(event, { allowAlt = false } = {}) {
  if (event.defaultPrevented || event.isComposing) return true;
  if (document.querySelector("dialog[open]")) return true;
  if (event.ctrlKey || event.metaKey || (!allowAlt && event.altKey)) {
    return true;
  }
  const target = event.target;
  if (target instanceof Element) {
    if (
      target.matches("input, textarea, select") ||
      target.isContentEditable ||
      target.closest(".CodeMirror, .cm-editor")
    ) {
      return true;
    }
  }
  return false;
}

function csrfHeaders() {
  const token = document.querySelector('meta[name="csrf-token"]');
  return token ? { "X-CSRF-Token": token.content } : {};
}

function handleProtectedResponse(response) {
  if (response.status === 401) {
    const next = window.location.pathname + window.location.search;
    window.location.href = "/login?next=" + encodeURIComponent(next);
    return new Promise(() => {});
  }
  return response;
}

function fetchJson(url, options = {}) {
  const headers = Object.assign(
    { Accept: "application/json" },
    options.headers || {}
  );
  return fetch(url, Object.assign({ cache: "no-store" }, options, { headers }))
    .then(handleProtectedResponse)
    .then((response) => {
      if (!response.ok) {
        throw new Error("Request failed with status " + response.status);
      }
      return response.json();
    });
}

function deleteEntry(entryId) {
  confirmDialog(
    uiText("confirm_delete_entry", {}, "Are you sure you want to delete this entry?"),
    { danger: true }
  ).then((confirmed) => {
    if (!confirmed) return;
    fetch("/delete_entry/" + entryId, {
      method: "DELETE",
      headers: csrfHeaders(),
    })
      .then(handleProtectedResponse)
      .then((Response) => {
        if (Response.ok) {
          window.location.href = "/entries";
        }
      });
  });
}

function renderClozeSentence(el, parts, matches, filled, blankedFallback) {
  if (!el) return;
  if (!Array.isArray(parts) || parts.length === 0) {
    el.textContent = blankedFallback || "";
    return;
  }
  el.textContent = "";
  const matchList = Array.isArray(matches) ? matches : [];
  const gapCount = Math.max(parts.length - 1, matchList.length);
  parts.forEach((part, idx) => {
    el.appendChild(document.createTextNode(part));
    if (idx < gapCount) {
      if (filled && idx < matchList.length) {
        const mark = document.createElement("mark");
        mark.className = "cloze-fill";
        mark.textContent = matchList[idx];
        el.appendChild(mark);
      } else if (!filled && idx < parts.length - 1) {
        const blank = document.createElement("span");
        blank.className = "cloze-blank";
        blank.textContent = "_____";
        el.appendChild(blank);
      }
    }
  });
}

function toggleQuizAnswer(button) {
  const card = button.closest(".quiz-card");
  if (!card) return;
  const answer = card.querySelector(".quiz-answer");
  if (!answer) return;
  const isHidden = answer.hidden;
  answer.hidden = !isHidden;
  button.textContent = isHidden
    ? uiText("hide_answer", {}, "Hide answer")
    : uiText("show_answer", {}, "Show answer");

  const sentenceEl = card.querySelector(".quiz-sentence");
  let parts = [];
  let matches = [];
  try {
    parts = JSON.parse(card.dataset.parts || "[]");
    matches = JSON.parse(card.dataset.matches || "[]");
  } catch (_) {}
  renderClozeSentence(sentenceEl, parts, matches, isHidden, card.dataset.blanked || "");

  if (isHidden && card.dataset.entryId && card.dataset.seen !== "true") {
    card.dataset.seen = "true";
    fetch("/quiz/" + encodeURIComponent(card.dataset.entryId) + "/seen", {
      method: "POST",
      headers: Object.assign({ Accept: "application/json" }, csrfHeaders()),
    })
      .then(handleProtectedResponse)
      .catch((err) => {
        console.error(err);
      });
  }
}

// The quiz card's "Try another" button: fetch a fresh question in place
// instead of a full page reload, keeping data-exclude synced with the
// server's recent history list.
document.addEventListener("DOMContentLoaded", function () {
  const nextBtn = document.getElementById("quiz-next-btn");
  if (!nextBtn) return;

  nextBtn.addEventListener("click", function (event) {
    event.preventDefault();
    const card = nextBtn.closest(".quiz-card");
    if (!card) return;

    const exclude = nextBtn.dataset.exclude || "";
    stopWordPronunciation();

    fetchJson("/quiz/next?exclude=" + encodeURIComponent(exclude))
      .then((data) => {
        if (!data.entry_id) {
          delete card.dataset.entryId;
          delete card.dataset.seen;
          card.querySelector(".quiz-sentence").textContent = uiText(
            "quiz_empty",
            {},
            "No quizzable entries yet — add some examples first."
          );
          nextBtn.hidden = true;
          return;
        }

        card.dataset.entryId = String(data.entry_id);
        card.dataset.headword = data.headword || data.word || "";
        card.dataset.blanked = data.blanked_sentence || "";
        card.dataset.parts = JSON.stringify(data.sentence_parts || []);
        card.dataset.matches = JSON.stringify(data.sentence_matches || []);
        delete card.dataset.seen;
        renderClozeSentence(
          card.querySelector(".quiz-sentence"),
          data.sentence_parts || [],
          data.sentence_matches || [],
          false,
          data.blanked_sentence
        );

        const answerEl = card.querySelector(".quiz-answer");
        answerEl.hidden = true;
        const wordEl = answerEl.querySelector(".quiz-answer-word") || answerEl.querySelector("strong");
        if (wordEl) wordEl.textContent = data.word;
        const ipaEl = answerEl.querySelector(".quiz-answer-ipa");
        if (ipaEl) {
          ipaEl.textContent = data.ipa || "";
          ipaEl.hidden = !data.ipa;
        }
        const linkEl = answerEl.querySelector(".quiz-answer-link") || answerEl.querySelector("a");
        if (linkEl) linkEl.href = "/entry/" + data.entry_id;
        const defEl = answerEl.querySelector(".quiz-answer-def");
        if (defEl) {
          defEl.textContent = data.definition_preview || "";
          defEl.hidden = !data.definition_preview;
        }

        const revealBtn = card.querySelector(".quiz-reveal-btn");
        revealBtn.textContent = uiText("show_answer", {}, "Show answer");

        nextBtn.dataset.exclude = data.next_exclude || "";
      })
      .catch((err) => {
        console.error(err);
      });
  });
});

function initQuickSearch() {
  const dialog = document.getElementById("quick-search-dialog");
  const input = document.getElementById("quick-search-input");
  const list = document.getElementById("quick-search-list");
  const openBtn = document.getElementById("open-quick-search");
  if (!dialog || !input || !list || typeof dialog.showModal !== "function") return;

  let activeIndex = -1;
  let debounceTimer = null;
  let abortController = null;
  let ignoreNextSlash = false;

  function setActive(index) {
    const items = list.querySelectorAll(".quick-search-item");
    if (!items.length) {
      activeIndex = -1;
      return;
    }
    activeIndex = ((index % items.length) + items.length) % items.length;
    items.forEach((li, i) => {
      li.classList.toggle("is-active", i === activeIndex);
      if (i === activeIndex) {
        li.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function renderItems(items, query) {
    list.textContent = "";
    activeIndex = -1;
    if (!items.length && !query) {
      const empty = document.createElement("li");
      empty.className = "quick-search-empty";
      empty.textContent = uiText("quick_search_hint", null, "Type to filter your words, ↑↓ to navigate, Enter to open");
      list.appendChild(empty);
      return;
    }
    if (!items.length) {
      const empty = document.createElement("li");
      empty.className = "quick-search-empty";
      empty.textContent = uiText("quick_search_empty", null, "No matching words.");
      list.appendChild(empty);
    } else {
      items.forEach((item) => {
        const li = document.createElement("li");
        li.className = "quick-search-item";
        li.setAttribute("role", "option");
        const a = document.createElement("a");
        a.href = "/entry/" + encodeURIComponent(item.id);
        const wordSpan = document.createElement("span");
        wordSpan.className = "quick-search-word";
        wordSpan.textContent = item.word || "";
        a.appendChild(wordSpan);
        if (item.context) {
          const ctxSpan = document.createElement("span");
          ctxSpan.className = "quick-search-ctx";
          ctxSpan.textContent = item.context;
          a.appendChild(ctxSpan);
        }
        li.appendChild(a);
        list.appendChild(li);
      });
    }
    if (query) {
      const allLi = document.createElement("li");
      allLi.className = "quick-search-item";
      allLi.setAttribute("role", "option");
      const a = document.createElement("a");
      a.href = "/entries?q=" + encodeURIComponent(query);
      const span = document.createElement("span");
      span.className = "quick-search-ctx";
      span.textContent = uiText("quick_search_see_all", { q: query }, 'Search all entries for "' + query + '" →');
      a.appendChild(span);
      allLi.appendChild(a);
      list.appendChild(allLi);
    }
    if (list.querySelector(".quick-search-item")) {
      setActive(0);
    }
  }

  function runQuery() {
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const q = input.value.trim();
    fetchJson("/api/v1/quick-search?q=" + encodeURIComponent(q) + "&limit=12", {
      signal: abortController.signal,
    })
      .then((data) => renderItems(Array.isArray(data.items) ? data.items : [], q))
      .catch((err) => {
        if (err.name !== "AbortError") console.error(err);
      });
  }

  function openQuickSearch({ fromSlash = false } = {}) {
    if (dialog.open) return;
    ignoreNextSlash = Boolean(fromSlash);
    input.value = "";
    dialog.showModal();
    input.focus();
    runQuery();
    if (ignoreNextSlash) {
      setTimeout(() => {
        ignoreNextSlash = false;
      }, 250);
    }
  }

  if (openBtn) {
    openBtn.addEventListener("click", () => openQuickSearch());
  }
  document.querySelectorAll("[data-open-quick-search]").forEach((btn) => {
    btn.addEventListener("click", () => openQuickSearch());
  });

  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) {
      dialog.close();
    }
  });

  input.addEventListener("input", function () {
    if (ignoreNextSlash && input.value.startsWith("/")) {
      input.value = input.value.slice(1);
      ignoreNextSlash = false;
    }
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(runQuery, 150);
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      event.preventDefault();
      dialog.close();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive(activeIndex + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive(activeIndex - 1);
    } else if (event.key === "Enter") {
      const active = list.querySelector(".quick-search-item.is-active a");
      if (active) {
        event.preventDefault();
        window.location.href = active.href;
      }
    }
  });

  document.addEventListener("keydown", function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (dialog.open) {
        dialog.close();
      } else {
        openQuickSearch();
      }
      return;
    }
    if (event.key === "/" && !shouldIgnoreShortcut(event)) {
      event.preventDefault();
      openQuickSearch({ fromSlash: true });
    }
  });
}

let activeAudio = null;
let activeAudioButton = null;
let activeAudioToken = 0;

function stopWordPronunciation() {
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
    } catch (_) {}
  }
}

function buildPronunciationUrls(word) {
  const clean = (word || "").trim();
  if (!clean) return [];
  const urls = [];
  if (!/\s/.test(clean)) {
    const slug = encodeURIComponent(clean.toLowerCase());
    urls.push("https://ssl.gstatic.com/dictionary/static/sounds/oxford/" + slug + "--_us_1.mp3");
    urls.push("https://ssl.gstatic.com/dictionary/static/sounds/oxford/x" + slug + "--_us_1.mp3");
  }
  urls.push(
    "https://www.google.com/speech-api/v1/synthesize?text=" +
      encodeURIComponent(clean) +
      "&enc=mpeg&lang=en-us&speed=0.45&client=lr-language-tts&use_google_only_voices=1"
  );
  return urls;
}

function playWordPronunciation(word, button) {
  const clean = (word || "").trim();
  if (!clean || !button) return;
  if (activeAudioButton === button) {
    stopWordPronunciation();
    return;
  }
  stopWordPronunciation();

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
    } catch (_) {
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

function getCsrfToken() {
  const token = document.querySelector('meta[name="csrf-token"]');
  return token ? token.content : "";
}

function initEntrySheet(article, { mode = "standalone", onUpdated, onDeleted, onCopy, signal } = {}) {
  if (!article) return;
  const entryId = article.dataset.entryId || "";
  const definitionId = article.dataset.definitionId || "";
  const csrfToken = getCsrfToken();
  const isSplit = mode === "split";
  const listenerOpts = signal ? { signal } : undefined;

  function notifyUpdated(meta) {
    if (typeof onUpdated === "function") {
      onUpdated(Object.assign({ entryId }, meta || {}));
    } else {
      location.reload();
    }
  }

  function notifyDeleted() {
    if (typeof onDeleted === "function") {
      onDeleted(entryId);
    } else {
      window.location.href = "/entries";
    }
  }

  const audioBtn = article.querySelector("#entry-audio-btn");
  if (audioBtn) {
    audioBtn.addEventListener("click", () => {
      playWordPronunciation(audioBtn.dataset.word || "", audioBtn);
    }, listenerOpts);
  }

  // Delete entry
  const delEntryBtn = article.querySelector('[data-action="delete-entry"]');
  if (delEntryBtn) {
    delEntryBtn.addEventListener("click", () => {
      confirmDialog(
        uiText("confirm_delete_entry", {}, "Are you sure you want to delete this entry?"),
        { danger: true }
      ).then((confirmed) => {
        if (!confirmed) return;
        fetch("/delete_entry/" + encodeURIComponent(entryId), {
          method: "DELETE",
          headers: csrfHeaders(),
        })
          .then(handleProtectedResponse)
          .then((resp) => {
            if (resp.ok) notifyDeleted();
          });
      });
    }, listenerOpts);
  }

  // Delete definition
  const delDefBtn = article.querySelector('[data-action="delete-definition"]');
  if (delDefBtn) {
    delDefBtn.addEventListener("click", () => {
      const defId = delDefBtn.dataset.definitionId || definitionId;
      if (!defId) return;
      confirmDialog(
        uiText("confirm_delete_def", null, "Are you sure you want to delete this definition?"),
        { danger: true }
      ).then((confirmed) => {
        if (!confirmed) return;
        fetch("/delete_definition/" + encodeURIComponent(defId), {
          method: "DELETE",
          headers: csrfHeaders(),
        })
          .then(handleProtectedResponse)
          .then((resp) => {
            if (resp.ok) notifyUpdated({ action: "delete-definition" });
          });
      });
    }, listenerOpts);
  }

  // Bookmark set / clear
  const setBmBtn = article.querySelector('[data-action="set-bookmark"]');
  if (setBmBtn) {
    setBmBtn.addEventListener("click", () => {
      fetch("/entry/" + encodeURIComponent(entryId) + "/set_review_bookmark", {
        method: "POST",
        headers: csrfHeaders(),
      })
        .then(handleProtectedResponse)
        .then((resp) => {
          if (resp.ok) notifyUpdated({ action: "bookmark", bookmarked: true });
          else showToast(uiText("bookmark_set_failed", null, "Failed to set resume point."), { type: "error" });
        });
    }, listenerOpts);
  }

  const clearBmBtn = article.querySelector('[data-action="clear-bookmark"]');
  if (clearBmBtn) {
    clearBmBtn.addEventListener("click", () => {
      fetch("/entry/" + encodeURIComponent(entryId) + "/clear_review_bookmark", {
        method: "POST",
        headers: csrfHeaders(),
      })
        .then(handleProtectedResponse)
        .then((resp) => {
          if (resp.ok) notifyUpdated({ action: "bookmark", bookmarked: false });
          else showToast(uiText("bookmark_clear_failed", null, "Failed to clear resume point."), { type: "error" });
        });
    }, listenerOpts);
  }

  // Inline Word/Context edit toggle & XHR submit
  const toggleEntryBtn = article.querySelector("#toggle-entry-edit");
  const toggleContextBtn = article.querySelector("#toggle-context-edit");
  const inlineEntryForm = article.querySelector("#inline-entry-form");
  const inlineEntryErr = article.querySelector("#inline-entry-error");
  const cancelEntryBtn = article.querySelector("#cancel-entry-edit");

  function setEntryEditOpen(open, focusFieldId) {
    if (!inlineEntryForm) return;
    inlineEntryForm.hidden = !open;
    if (inlineEntryErr) inlineEntryErr.hidden = true;
    if (toggleEntryBtn) toggleEntryBtn.classList.toggle("active", open);
    if (toggleContextBtn) toggleContextBtn.classList.toggle("active", open);
    if (open) {
      inlineEntryForm.scrollIntoView({ behavior: "smooth", block: "nearest" });
      const input = article.querySelector("#" + (focusFieldId || "inline-word-input"));
      if (input) input.focus();
    }
  }

  if (toggleEntryBtn && inlineEntryForm) {
    toggleEntryBtn.addEventListener("click", () => {
      setEntryEditOpen(inlineEntryForm.hidden, "inline-word-input");
    }, listenerOpts);
  }
  if (toggleContextBtn && inlineEntryForm) {
    toggleContextBtn.addEventListener("click", () => {
      setEntryEditOpen(true, "inline-context-input");
    }, listenerOpts);
  }
  if (cancelEntryBtn && inlineEntryForm) {
    cancelEntryBtn.addEventListener("click", () => setEntryEditOpen(false), listenerOpts);
  }
  if (inlineEntryForm) {
    inlineEntryForm.addEventListener("submit", (event) => {
      event.preventDefault();
      if (inlineEntryErr) inlineEntryErr.hidden = true;
      const fd = new FormData(inlineEntryForm);
      if (!fd.get("csrf_token")) fd.set("csrf_token", csrfToken);
      fetch("/edit_entry/" + encodeURIComponent(entryId), {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
        body: fd,
      })
        .then(handleProtectedResponse)
        .then((resp) =>
          resp.json().catch(() => ({})).then((data) => ({ ok: resp.ok, data }))
        )
        .then(({ ok, data }) => {
          if (ok) {
            showToast(uiText("entry_updated_toast", null, "Saved"));
            notifyUpdated({ action: "edit-entry", word: data.word, context: data.context });
          } else {
            const msg = (data && data.detail) || uiText("entry_save_failed", null, "Could not save changes.");
            if (inlineEntryErr) {
              inlineEntryErr.textContent = msg;
              inlineEntryErr.hidden = false;
            } else {
              showToast(msg, { type: "error" });
            }
          }
        })
        .catch(() => {
          showToast(uiText("entry_save_failed", null, "Could not save changes."), { type: "error" });
        });
    }, listenerOpts);
  }

  let rawCache = null;
  function ensureRawLoaded() {
    if (rawCache) return Promise.resolve(rawCache);
    return fetchJson("/entry/" + encodeURIComponent(entryId) + "/raw").then((data) => {
      rawCache = data || { definition_text: "", example_text: "" };
      return rawCache;
    });
  }

  // Inline Definition edit/add
  const toggleDefBtn = article.querySelector("#toggle-def-edit");
  const inlineDefForm = article.querySelector("#inline-def-form");
  const cancelDefBtn = article.querySelector("#cancel-def-edit");
  const defDiv = article.querySelector("#definition-div");
  if (toggleDefBtn && inlineDefForm) {
    toggleDefBtn.addEventListener("click", () => {
      const opening = inlineDefForm.hidden;
      inlineDefForm.hidden = !opening;
      if (defDiv) defDiv.hidden = opening;
      if (opening) {
        const ta = article.querySelector("#inline-def-textarea");
        ensureRawLoaded()
          .then((data) => {
            if (ta && !ta.value) ta.value = data.definition_text || "";
            if (ta) ta.focus();
          })
          .catch(() => {
            if (ta) ta.focus();
          });
      }
    }, listenerOpts);
  }
  if (cancelDefBtn && inlineDefForm) {
    cancelDefBtn.addEventListener("click", () => {
      inlineDefForm.hidden = true;
      if (defDiv) defDiv.hidden = false;
    }, listenerOpts);
  }
  if (inlineDefForm) {
    inlineDefForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const ta = article.querySelector("#inline-def-textarea");
      const text = ta ? ta.value.trim() : "";
      if (!text) return;
      const fd = new FormData();
      fd.append("csrf_token", csrfToken);
      fd.append("definition_text", text);
      let url = "/edit_definition/" + encodeURIComponent(definitionId);
      const isAdd = !definitionId;
      if (isAdd) {
        url = "/add_definition";
        fd.append("entry_id", entryId);
      }
      fetch(url, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
        body: fd,
      })
        .then(handleProtectedResponse)
        .then((resp) => {
          if (resp.ok) {
            showToast(uiText("entry_updated_toast", null, "Saved"));
            notifyUpdated({ action: isAdd ? "add-definition" : "edit-definition" });
          } else {
            showToast(uiText("entry_save_failed", null, "Could not save changes."), { type: "error" });
          }
        })
        .catch(() => {
          showToast(uiText("entry_save_failed", null, "Could not save changes."), { type: "error" });
        });
    }, listenerOpts);
  }

  // Inline Example edit
  const toggleExBtn = article.querySelector("#edit-example");
  const inlineExForm = article.querySelector("#inline-example-form");
  const cancelExBtn = article.querySelector("#cancel-example-edit");
  const exDiv = article.querySelector("#example-div");
  if (toggleExBtn && inlineExForm) {
    toggleExBtn.addEventListener("click", () => {
      const opening = inlineExForm.hidden;
      inlineExForm.hidden = !opening;
      if (exDiv) exDiv.hidden = opening;
      if (opening) {
        const ta = article.querySelector("#inline-example-textarea");
        ensureRawLoaded()
          .then((data) => {
            if (ta && !ta.value) ta.value = data.example_text || "";
            if (ta) ta.focus();
          })
          .catch(() => {
            if (ta) ta.focus();
          });
      }
    }, listenerOpts);
  }
  if (cancelExBtn && inlineExForm) {
    cancelExBtn.addEventListener("click", () => {
      inlineExForm.hidden = true;
      if (exDiv) exDiv.hidden = false;
    }, listenerOpts);
  }
  if (inlineExForm) {
    inlineExForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const ta = article.querySelector("#inline-example-textarea");
      const fd = new FormData();
      fd.append("csrf_token", csrfToken);
      fd.append("example_text", ta ? ta.value : "");
      fetch("/edit_example/" + encodeURIComponent(entryId), {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
        body: fd,
      })
        .then(handleProtectedResponse)
        .then((resp) => {
          if (resp.ok) {
            showToast(uiText("entry_updated_toast", null, "Saved"));
            notifyUpdated({ action: "edit-example" });
          } else {
            showToast(uiText("entry_save_failed", null, "Could not save changes."), { type: "error" });
          }
        })
        .catch(() => {
          showToast(uiText("entry_save_failed", null, "Could not save changes."), { type: "error" });
        });
    }, listenerOpts);
  }

  // Lazy Synonyms section
  const synDetails = article.querySelector("#entry-synonyms-details");
  const synPanel = article.querySelector("#entry-synonyms-panel");
  let synLoaded = false;
  if (synDetails && synPanel) {
    synDetails.addEventListener("toggle", () => {
      if (!synDetails.open || synLoaded) return;
      synLoaded = true;
      synPanel.textContent = uiText("synonyms_loading", null, "Loading synonyms…");
      const word = article.dataset.word || "";
      fetchJson("/api/v1/lookup?word=" + encodeURIComponent(word) + "&include_synonym_links=true")
        .then((data) => {
          synPanel.textContent = "";
          if (data.thesaurus_error) {
            const p = document.createElement("p");
            p.className = "quiz-empty";
            p.textContent = uiText("synonyms_error", null, "Thesaurus lookup temporarily unavailable.");
            synPanel.appendChild(p);
            return;
          }
          const senses = Array.isArray(data.senses) ? data.senses : [];
          if (!senses.length) {
            const p = document.createElement("p");
            p.className = "quiz-empty";
            p.textContent = uiText("synonyms_empty", null, "No synonyms found for this word.");
            synPanel.appendChild(p);
            return;
          }
          const links = data.synonym_links || {};
          const table = document.createElement("table");
          table.className = "synonyms-table";
          const tbody = document.createElement("tbody");
          senses.forEach((sense) => {
            const tr = document.createElement("tr");
            const tdPos = document.createElement("td");
            tdPos.textContent = sense.part_of_speech || "";
            const tdMean = document.createElement("td");
            tdMean.textContent = sense.meaning || "";
            const tdSyns = document.createElement("td");
            const syns = Array.isArray(sense.synonyms) ? sense.synonyms : [];
            syns.forEach((syn, idx) => {
              if (idx > 0) tdSyns.appendChild(document.createTextNode(", "));
              const linkedId = links[String(syn).toLowerCase()];
              if (linkedId) {
                const a = document.createElement("a");
                a.href = "/entry/" + encodeURIComponent(linkedId);
                a.textContent = syn;
                tdSyns.appendChild(a);
              } else {
                tdSyns.appendChild(document.createTextNode(syn));
              }
            });
            tr.appendChild(tdPos);
            tr.appendChild(tdMean);
            tr.appendChild(tdSyns);
            tbody.appendChild(tr);
          });
          table.appendChild(tbody);
          synPanel.appendChild(table);
        })
        .catch(() => {
          synPanel.textContent = uiText("synonyms_error", null, "Thesaurus lookup temporarily unavailable.");
        });
    }, listenerOpts);
  }

  // Shortcuts dialog (standalone only)
  const shortcutsDialog = !isSplit ? document.getElementById("entry-shortcuts-dialog") : null;
  const openShortcutsBtn = !isSplit ? article.querySelector("#open-entry-shortcuts") : null;
  const closeShortcutsBtn = !isSplit ? document.getElementById("close-entry-shortcuts") : null;
  if (openShortcutsBtn && shortcutsDialog) {
    openShortcutsBtn.addEventListener("click", () => shortcutsDialog.showModal(), listenerOpts);
  }
  if (closeShortcutsBtn && shortcutsDialog) {
    closeShortcutsBtn.addEventListener("click", () => shortcutsDialog.close(), listenerOpts);
  }
  if (shortcutsDialog) {
    shortcutsDialog.addEventListener("click", (event) => {
      if (event.target === shortcutsDialog) shortcutsDialog.close();
    }, listenerOpts);
  }

  document.addEventListener("keydown", (event) => {
    if (shouldIgnoreShortcut(event)) return;
    if (event.key === "p") {
      if (audioBtn) audioBtn.click();
    } else if (event.key === "e") {
      if (toggleExBtn) toggleExBtn.click();
    } else if (event.key === "Q") {
      const textToCopy = article.dataset.entryText || "";
      if (typeof onCopy === "function") {
        onCopy(textToCopy);
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(textToCopy).then(() => {
          showToast(uiText("entry_copied", null, "Copied to clipboard"));
        }).catch(() => {});
      }
    } else if (!isSplit) {
      if (event.key === "?" && shortcutsDialog) {
        event.preventDefault();
        shortcutsDialog.showModal();
      } else if (event.key === "b") {
        if (document.referrer && new URL(document.referrer).origin === window.location.origin) {
          history.back();
        } else {
          window.location.href = "/entries";
        }
      } else if (event.key === "D" && delEntryBtn) {
        delEntryBtn.click();
      } else if (event.key === "a") {
        window.open("/add_entry", "_blank").focus();
      } else if (event.key === "A") {
        window.location.href = "/add_entry";
      }
    }
  }, listenerOpts);
}

// Close the header account menu on outside click or Escape, restoring focus.
document.addEventListener("click", function (event) {
  document.querySelectorAll("details.nav-account-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) {
      menu.open = false;
    }
  });
});

document.addEventListener("keydown", function (event) {
  if (event.key !== "Escape") return;
  document.querySelectorAll("details.nav-account-menu[open]").forEach((menu) => {
    const hadFocus = menu.contains(document.activeElement);
    menu.open = false;
    if (hadFocus) {
      const summary = menu.querySelector("summary");
      if (summary) summary.focus();
    }
  });
});

document.addEventListener("DOMContentLoaded", function () {
  applyThemePreference(getThemePreference());
  initRailAndDrawer();
  initQuickSearch();
  document.querySelectorAll(".quiz-card").forEach((card) => {
    const sentenceEl = card.querySelector(".quiz-sentence");
    if (!sentenceEl) return;
    try {
      const parts = JSON.parse(card.dataset.parts || "[]");
      const matches = JSON.parse(card.dataset.matches || "[]");
      if (parts.length > 1) {
        renderClozeSentence(sentenceEl, parts, matches, false, card.dataset.blanked || "");
      }
    } catch (_) {}
  });
  document.querySelectorAll(".theme-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const current = getThemePreference();
      const next = current === "auto" ? "light" : current === "light" ? "dark" : "auto";
      applyThemePreference(next);
    });
  });
  document.querySelectorAll(".theme-seg-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      applyThemePreference(btn.dataset.themeValue || "auto");
    });
  });

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const msg = form.dataset.confirm || (form.dataset.confirmKey ? uiText(form.dataset.confirmKey, null, form.dataset.confirmKey) : "");
    if (!msg || form.dataset.confirmed === "true") return;
    event.preventDefault();
    confirmDialog(msg, { danger: form.dataset.confirmDanger === "true" }).then((ok) => {
      if (ok) {
        form.dataset.confirmed = "true";
        form.submit();
      }
    });
  });
});
