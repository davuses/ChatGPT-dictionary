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
        location.reload();
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

// The quiz card's "next question" button (dashboard's "Try another", or
// anywhere else quiz_card() is used with an action_id): fetch a fresh
// question in place instead of a full page reload. The button's href is
// kept in sync with the server's exclude-list response as a fallback (new
// tab / JS failure still shows a fresh question via GET /quiz/next, just
// as a normal navigation).
document.addEventListener("DOMContentLoaded", function () {
  const nextBtn = document.getElementById("quiz-next-btn");
  if (!nextBtn) return;

  nextBtn.addEventListener("click", function (event) {
    event.preventDefault();
    const card = nextBtn.closest(".quiz-card");
    if (!card) return;

    const url = new URL(nextBtn.href, window.location.href);
    const exclude = url.searchParams.get("exclude") || "";

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

        nextBtn.href = "/quiz/next?exclude=" + encodeURIComponent(data.next_exclude);
      })
      .catch((err) => {
        console.error(err);
      });
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
