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
        delete card.dataset.seen;
        card.querySelector(".quiz-sentence").textContent = data.blanked_sentence;

        const answerEl = card.querySelector(".quiz-answer");
        answerEl.hidden = true;
        answerEl.querySelector("strong").textContent = data.word;
        answerEl.querySelector("a").href = "/entry/" + data.entry_id;

        const revealBtn = card.querySelector(".quiz-reveal-btn");
        revealBtn.textContent = uiText("show_answer", {}, "Show answer");

        nextBtn.dataset.exclude = data.next_exclude || "";
      })
      .catch((err) => {
        console.error(err);
      });
  });
});

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

  const editors = document.querySelectorAll("textarea.markdown-editor");
  if (!editors.length || typeof EasyMDE === "undefined") return;

  const hasAutoFocusInput = Boolean(document.querySelector("input[autofocus]"));
  editors.forEach(function (textarea, index) {
    new EasyMDE({
      element: textarea,
      autofocus: !hasAutoFocusInput && index === 0,
      // Font Awesome is vendored in static/ and linked from base.html.jinja;
      // without this EasyMDE injects a maxcdn.bootstrapcdn.com <link>, which
      // leaves the toolbar as tofu boxes whenever that CDN is unreachable.
      autoDownloadFontAwesome: false,
      spellChecker: false,
      nativeSpellcheck: true,
      inputStyle: "contenteditable",
      toolbar: [
        "bold",
        "italic",
        "strikethrough",
        "quote",
        "|",
        "unordered-list",
        "ordered-list",
        "link",
        "table",
        "heading",
        "|",
        "preview",
        "side-by-side",
        "fullscreen",
      ],
    });
  });

  const mdEditors = document.querySelectorAll(".CodeMirror");
  mdEditors.forEach(function (mdEditor) {
    mdEditor.addEventListener("keydown", function (event) {
      if (event.shiftKey && event.key === "Enter") {
        event.preventDefault();
        const form = mdEditor.closest("form");
        if (form) {
          form.requestSubmit();
        }
      }
    });
  });
});
