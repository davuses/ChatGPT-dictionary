import { EditorState } from "@codemirror/state";
import { EditorView, keymap, placeholder as cmPlaceholder } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { markdown } from "@codemirror/lang-markdown";
import { GFM } from "@lezer/markdown";
import { tags } from "@lezer/highlight";

const mdHighlight = HighlightStyle.define([
  { tag: tags.heading1, fontWeight: "700", fontSize: "1.45em", color: "var(--heading)" },
  { tag: tags.heading2, fontWeight: "700", fontSize: "1.25em", color: "var(--heading)" },
  { tag: tags.heading3, fontWeight: "700", fontSize: "1.12em", color: "var(--heading)" },
  { tag: [tags.heading4, tags.heading5, tags.heading6], fontWeight: "700", color: "var(--heading)" },
  { tag: tags.strong, fontWeight: "700", color: "var(--heading)" },
  { tag: tags.emphasis, fontStyle: "italic" },
  { tag: tags.strikethrough, textDecoration: "line-through", color: "var(--muted)" },
  { tag: tags.quote, color: "var(--muted)", fontStyle: "italic" },
  { tag: tags.monospace, fontFamily: "var(--font-mono)", backgroundColor: "var(--code-bg)", borderRadius: "3px", padding: "0 3px" },
  { tag: tags.link, color: "var(--accent)", textDecoration: "underline" },
  { tag: tags.url, color: "var(--muted)", fontFamily: "var(--font-mono)", fontSize: "0.9em" },
  // Dimmed raw Markdown syntax tokens (**, *, #, >, ~~, `, etc.)
  { tag: [tags.processingInstruction, tags.meta, tags.contentSeparator], color: "var(--muted)", opacity: "0.45", fontFamily: "var(--font-mono)", fontWeight: "400" },
]);

const editorTheme = EditorView.theme({
  "&": {
    backgroundColor: "var(--surface-elevated)",
    color: "var(--ink)",
  },
  ".cm-content": {
    caretColor: "var(--accent)",
    padding: "4px 0",
  },
  ".cm-cursor, .cm-dropCursor": {
    borderLeftColor: "var(--accent)",
  },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": {
    backgroundColor: "var(--accent-soft)",
  },
  ".cm-activeLine": {
    backgroundColor: "transparent",
  },
  ".cm-placeholder": {
    color: "var(--muted)",
    opacity: "0.75",
  },
});

function wrapSelection(view, before, after = before, fallback = "") {
  const { from, to } = view.state.selection.main;
  const selected = view.state.sliceDoc(from, to) || fallback;
  view.dispatch({
    changes: { from, to, insert: before + selected + after },
    selection: { anchor: from + before.length, head: from + before.length + selected.length },
  });
  view.focus();
}

function prefixLines(view, prefix) {
  const { from, to } = view.state.selection.main;
  const startLine = view.state.doc.lineAt(from);
  const endLine = view.state.doc.lineAt(to);
  const changes = [];
  for (let ln = startLine.number; ln <= endLine.number; ln++) {
    const line = view.state.doc.line(ln);
    changes.push({ from: line.from, to: line.from, insert: prefix });
  }
  view.dispatch({ changes });
  view.focus();
}

function mountMarkdownEditor(textarea, { autofocus = false } = {}) {
  if (textarea.dataset.cmMounted === "true") return;
  textarea.dataset.cmMounted = "true";

  const wrap = document.createElement("div");
  wrap.className = "cm-md-wrap";

  const toolbar = document.createElement("div");
  toolbar.className = "cm-md-toolbar";
  toolbar.setAttribute("role", "toolbar");
  toolbar.setAttribute("aria-label", "Markdown formatting");

  const host = document.createElement("div");
  host.className = "cm-md-host";

  const preview = document.createElement("div");
  preview.className = "cm-md-preview markdown-body";
  preview.hidden = true;

  wrap.appendChild(toolbar);
  wrap.appendChild(host);
  wrap.appendChild(preview);

  textarea.parentNode.insertBefore(wrap, textarea);
  textarea.hidden = true;

  let view = null;

  const submitKeymap = keymap.of([
    {
      key: "Mod-Enter",
      run() {
        const form = textarea.closest("form");
        if (form) {
          form.requestSubmit();
          return true;
        }
        return false;
      },
    },
  ]);

  const extensions = [
    history(),
    EditorView.lineWrapping,
    markdown({ extensions: [GFM] }),
    syntaxHighlighting(mdHighlight),
    editorTheme,
    submitKeymap,
    keymap.of([indentWithTab, ...defaultKeymap, ...historyKeymap]),
    EditorView.contentAttributes.of({ spellcheck: "true" }),
    EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        textarea.value = update.state.doc.toString();
      }
    }),
  ];

  if (textarea.placeholder) {
    extensions.push(cmPlaceholder(textarea.placeholder));
  }

  view = new EditorView({
    state: EditorState.create({
      doc: textarea.value || "",
      extensions,
    }),
    parent: host,
  });

  if (autofocus) {
    view.focus();
  }

  const formatButtons = [];

  function addBtn(label, title, onClick, { extraClass = "", isFormat = false, strike = false } = {}) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cm-md-btn" + (extraClass ? " " + extraClass : "");
    if (strike) {
      const s = document.createElement("s");
      s.textContent = label;
      btn.appendChild(s);
    } else {
      btn.textContent = label;
    }
    btn.title = title;
    btn.setAttribute("aria-label", title);
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      onClick(btn);
    });
    toolbar.appendChild(btn);
    if (isFormat) formatButtons.push(btn);
    return btn;
  }

  function addSep() {
    const sep = document.createElement("span");
    sep.className = "cm-md-sep";
    sep.setAttribute("aria-hidden", "true");
    toolbar.appendChild(sep);
  }

  addBtn("B", "Bold", () => wrapSelection(view, "**", "**", "bold"), { isFormat: true });
  addBtn("I", "Italic", () => wrapSelection(view, "*", "*", "italic"), { extraClass: "cm-md-btn--italic", isFormat: true });
  addBtn("S", "Strikethrough", () => wrapSelection(view, "~~", "~~", "text"), { strike: true, isFormat: true });
  addBtn("“", "Blockquote", () => prefixLines(view, "> "), { isFormat: true });
  addSep();
  addBtn("•", "Bullet list", () => prefixLines(view, "- "), { isFormat: true });
  addBtn("1.", "Numbered list", () => prefixLines(view, "1. "), { isFormat: true });
  addBtn("H", "Heading", () => prefixLines(view, "## "), { isFormat: true });
  addBtn("Link", "Insert link", () => wrapSelection(view, "[", "](https://)", "text"), { isFormat: true });

  const spacer = document.createElement("span");
  spacer.className = "cm-md-spacer";
  toolbar.appendChild(spacer);

  let previewActive = false;
  addBtn("Preview", "Toggle preview", (btn) => {
    previewActive = !previewActive;
    btn.classList.toggle("is-active", previewActive);
    formatButtons.forEach((fb) => {
      fb.disabled = previewActive;
    });
    if (!previewActive) {
      preview.hidden = true;
      host.hidden = false;
      view.focus();
      return;
    }
    host.hidden = true;
    preview.hidden = false;
    preview.textContent = "Rendering…";
    const headers = Object.assign(
      { "Content-Type": "application/json", Accept: "application/json" },
      typeof window.csrfHeaders === "function" ? window.csrfHeaders() : {}
    );
    fetch("/markdown/preview", {
      method: "POST",
      headers,
      body: JSON.stringify({ text: view.state.doc.toString() }),
    })
      .then((resp) => {
        if (!resp.ok) throw new Error("Preview failed");
        return resp.json();
      })
      .then((data) => {
        preview.innerHTML = (data && data.html) || "";
      })
      .catch(() => {
        preview.textContent = "Preview unavailable.";
      });
  });

  addBtn("⛶", "Toggle fullscreen", (btn) => {
    const fs = wrap.classList.toggle("is-fullscreen");
    btn.classList.toggle("is-active", fs);
  });
}

function initGlossbookMarkdownEditors() {
  const editors = document.querySelectorAll("textarea.markdown-editor");
  if (!editors.length) return;
  const hasAutoFocusInput = Boolean(document.querySelector("input[autofocus]"));
  editors.forEach((ta, idx) => {
    mountMarkdownEditor(ta, { autofocus: !hasAutoFocusInput && idx === 0 });
  });
}

window.initGlossbookMarkdownEditors = initGlossbookMarkdownEditors;
document.addEventListener("DOMContentLoaded", initGlossbookMarkdownEditors);
