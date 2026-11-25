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
  if (meta) meta.setAttribute("content", isDark ? "#0f171c" : "#f8f9fa");

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
  if (!filled || !Array.isArray(parts) || parts.length === 0) {
    el.textContent = blankedFallback || "";
    return;
  }
  el.textContent = "";
  parts.forEach((part, idx) => {
    el.appendChild(document.createTextNode(part));
    if (idx < (matches ? matches.length : 0)) {
      const strong = document.createElement("strong");
      strong.textContent = matches[idx];
      el.appendChild(strong);
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
        card.querySelector(".quiz-sentence").textContent = data.blanked_sentence;

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

  function openQuickSearch() {
    if (dialog.open) return;
    input.value = "";
    dialog.showModal();
    input.focus();
    runQuery();
  }

  if (openBtn) {
    openBtn.addEventListener("click", openQuickSearch);
  }

  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) {
      dialog.close();
    }
  });

  input.addEventListener("input", function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(runQuery, 150);
  });

  input.addEventListener("keydown", function (event) {
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
      openQuickSearch();
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
  initQuickSearch();
  document.querySelectorAll(".theme-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const current = getThemePreference();
      const next = current === "auto" ? "light" : current === "light" ? "dark" : "auto";
      applyThemePreference(next);
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
