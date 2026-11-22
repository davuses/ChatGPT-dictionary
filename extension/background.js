chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((err) => console.error("setPanelBehavior failed:", err));

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "jot-to-dictionary",
      title: "Jot to My Dictionary",
      contexts: ["selection", "page"],
    });
  });
});

function extractPageCapture() {
  const host = window.location.hostname.toLowerCase();
  const isYouTube =
    host === "youtu.be" ||
    host === "youtube.com" ||
    host.endsWith(".youtube.com");

  let word = "";
  let context = "";
  let timestampSeconds = null;

  const selection = window.getSelection();
  const selectedText = selection ? selection.toString().trim() : "";

  if (selectedText) {
    if (selectedText.split(/\s+/).length <= 6) {
      word = selectedText;
      if (selection.rangeCount > 0) {
        let node = selection.getRangeAt(0).commonAncestorContainer;
        if (node.nodeType === Node.TEXT_NODE) {
          node = node.parentElement;
        }
        const block =
          node && node.closest
            ? node.closest("p, li, blockquote, dd, td, article, section, div")
            : null;
        const blockText = (block ? block.innerText : "")
          .replace(/\s+/g, " ")
          .trim();
        if (blockText && blockText.length > selectedText.length) {
          const sentences = blockText.match(/[^.!?]+(?:[.!?]+|$)/g) || [
            blockText,
          ];
          const lowerSel = selectedText.toLowerCase();
          const matched = sentences.find((s) =>
            s.toLowerCase().includes(lowerSel)
          );
          context = (matched || blockText).trim();
          if (context.length > 400) {
            context = context.slice(0, 400).trim();
          }
        }
      }
    } else {
      context = selectedText.replace(/\s+/g, " ").trim();
    }
  }

  if (isYouTube) {
    const video =
      document.querySelector("#movie_player video.html5-main-video") ||
      document.querySelector("video");
    if (video && Number.isFinite(video.currentTime)) {
      timestampSeconds = Math.max(0, Math.floor(video.currentTime));
    }
    if (!context) {
      const segments = Array.from(
        document.querySelectorAll(".ytp-caption-segment")
      )
        .map((el) => (el.textContent || "").trim())
        .filter(Boolean);
      if (segments.length) {
        context = segments.join(" ").replace(/\s+/g, " ").trim();
      }
    }
  }

  return {
    url: window.location.href,
    title: document.title || "",
    word,
    context,
    timestampSeconds,
  };
}

function seekYouTubeVideo(targetSeconds) {
  const video =
    document.querySelector("#movie_player video.html5-main-video") ||
    document.querySelector("video");
  if (!video) return false;
  video.currentTime = Math.max(0, Number(targetSeconds) - 2);
  video.play().catch(() => {});
  return true;
}

async function captureTabAndStore(tab, fallbackSelection = "") {
  if (!tab || !tab.id || !tab.url || !/^https?:\/\//i.test(tab.url)) {
    return;
  }
  let captured = {
    url: tab.url,
    title: tab.title || "",
    word: fallbackSelection.trim(),
    context: "",
    timestampSeconds: null,
  };
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractPageCapture,
    });
    if (results && results[0] && results[0].result) {
      captured = results[0].result;
      if (!captured.word && fallbackSelection.trim()) {
        captured.word = fallbackSelection.trim();
      }
    }
  } catch (err) {
    console.warn("Could not read page capture:", err);
  }
  await chrome.storage.session.set({
    pendingCapture: Object.assign({}, captured, { capturedAt: Date.now() }),
  });
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== "jot-to-dictionary" || !tab) return;
  // Open side panel synchronously first to keep Chrome's user-gesture token.
  chrome.sidePanel
    .open({ windowId: tab.windowId })
    .catch((err) => console.error("sidePanel.open failed:", err));
  captureTabAndStore(tab, info.selectionText || "");
});

chrome.commands.onCommand.addListener((command, tab) => {
  if (command !== "quick-jot" || !tab) return;
  chrome.sidePanel
    .open({ windowId: tab.windowId })
    .catch((err) => console.error("sidePanel.open failed:", err));
  captureTabAndStore(tab);
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || typeof message !== "object") return false;

  if (message.type === "grabFromActiveTab") {
    chrome.tabs
      .query({ active: true, currentWindow: true })
      .then(async ([tab]) => {
        if (!tab || !tab.id || !tab.url || !/^https?:\/\//i.test(tab.url)) {
          sendResponse({ ok: false, error: "Active tab is not an HTTP(S) page." });
          return;
        }
        try {
          const results = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: extractPageCapture,
          });
          const data = results && results[0] && results[0].result;
          sendResponse({ ok: true, data });
        } catch (err) {
          sendResponse({ ok: false, error: String(err) });
        }
      });
    return true;
  }

  if (message.type === "seekYouTube") {
    chrome.tabs
      .query({ active: true, currentWindow: true })
      .then(async ([tab]) => {
        if (!tab || !tab.id) {
          sendResponse({ ok: false });
          return;
        }
        try {
          const results = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: seekYouTubeVideo,
            args: [message.seconds],
          });
          sendResponse({ ok: Boolean(results && results[0] && results[0].result) });
        } catch (_err) {
          sendResponse({ ok: false });
        }
      });
    return true;
  }

  return false;
});
