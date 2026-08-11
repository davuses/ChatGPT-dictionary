function deleteEntry(entryId) {
  if (confirm("Are you sure you want to delete this entry?")) {
    fetch("/delete_entry/" + entryId, { method: "DELETE" }).then((Response) => {
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
}

// "Next question" on /quiz: fetch a fresh question in place instead of a
// full page reload. The button's href is kept in sync with the server's
// exclude-list response as a fallback (new tab / JS failure still works,
// just as a normal navigation).
document.addEventListener("DOMContentLoaded", function () {
  const nextBtn = document.getElementById("quiz-next-btn");
  if (!nextBtn) return;

  nextBtn.addEventListener("click", function (event) {
    event.preventDefault();
    const card = nextBtn.closest(".quiz-card");
    if (!card) return;

    const url = new URL(nextBtn.href, window.location.href);
    const exclude = url.searchParams.get("exclude") || "";

    fetch("/quiz/next?exclude=" + encodeURIComponent(exclude), {
      cache: "no-store",
    })
      .then((response) => response.json())
      .then((data) => {
        if (!data.entry_id) {
          card.querySelector(".quiz-sentence").textContent =
            "No quizzable entries yet — add some examples first.";
          nextBtn.hidden = true;
          return;
        }

        card.querySelector(".quiz-sentence").textContent = data.blanked_sentence;

        const answerEl = card.querySelector(".quiz-answer");
        answerEl.hidden = true;
        answerEl.querySelector("strong").textContent = data.word;
        answerEl.querySelector("a").href = "/entry/" + data.entry_id;

        const revealBtn = card.querySelector(".quiz-reveal-btn");
        revealBtn.textContent = "Show answer";

        nextBtn.href = "/quiz?exclude=" + encodeURIComponent(data.next_exclude);
      });
  });
});

const editPagePattern = /\/edit_.*?|add_.*/;

if (editPagePattern.test(window.location.href)) {
  document.addEventListener("DOMContentLoaded", function () {
    var editor = new EasyMDE({
      autofocus: true,
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
    const mdEditors = document.querySelectorAll(".CodeMirror");
    mdEditors.forEach(function (mdEditor) {
      mdEditor.addEventListener("keydown", function (event) {
        if (event.shiftKey && event.key === "Enter") {
          event.preventDefault();
          const form = mdEditor.closest("form");
          if (form) {
            form.submit();
          }
        }
      });
    });
  });
}
