function deleteEntry(entryId) {
  if (confirm("Are you sure you want to delete this entry?")) {
    fetch("/delete_entry/" + entryId, { method: "DELETE" }).then((Response) => {
      if (Response.ok) {
        location.reload();
      }
    });
  }
}

const editPagePattern = /\/edit_.*?|add_.*/;

if (editPagePattern.test(window.location.href)) {
  document.addEventListener("DOMContentLoaded", function () {
    var editor = new EasyMDE({
      autofocus: true,
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
