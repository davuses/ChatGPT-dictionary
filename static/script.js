function shouldIgnoreShortcut(event, { allowAlt = false } = {}) {
  if (event.defaultPrevented || event.isComposing) return true;
  if (event.ctrlKey || event.metaKey || (!allowAlt && event.altKey)) {
    return true;
  }
  const target = event.target;
  if (target instanceof Element) {
    if (
      target.matches("input, textarea, select") ||
      target.isContentEditable ||
      target.closest(".CodeMirror")
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
  if (confirm("Are you sure you want to delete this entry?")) {
    fetch("/delete_entry/" + entryId, {
      method: "DELETE",
      headers: csrfHeaders(),
    }).then(handleProtectedResponse).then((Response) => {
      if (Response.ok) {
        window.location.href = "/entries";
      }
    });
  }
}

function toggleQuizAnswer(button) {
  const card = button.closest(".quiz-card");
  if (!card) return;
  const answer = card.querySelector(".quiz-answer");
  if (!answer) return;
  const isHidden = answer.hidden;
  answer.hidden = !isHidden;
  button.textContent = isHidden ? "Hide answer" : "Show answer";
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
          card.querySelector(".quiz-sentence").textContent =
            "No quizzable entries yet — add some examples first.";
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
        revealBtn.textContent = "Show answer";

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
    urls.push(
      "https://ssl.gstatic.com/dictionary/static/sounds/oxford/" +
        encodeURIComponent(clean.toLowerCase()) +
        "--_us_1.mp3"
    );
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
