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

async function extractPageCapture(hintWord = "") {
  const host = window.location.hostname.toLowerCase();
  const isYouTube =
    host === "youtu.be" ||
    host === "youtube.com" ||
    host.endsWith(".youtube.com");

  function parseTimestampText(raw) {
    const clean = (raw || "").trim();
    const match = clean.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (!match) return null;
    if (match[3] !== undefined) {
      return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
    }
    return Number(match[1]) * 60 + Number(match[2]);
  }

  function extractSentenceFromSegments(segments, targetSec, targetWord) {
    if (!segments.length) return "";
    const winStart = Math.max(0, targetSec - 28);
    const winEnd = targetSec + 12;
    const inWindow = segments.filter(
      (s) => s.start >= winStart && s.start <= winEnd && s.text
    );
    if (!inWindow.length) return "";

    let fullText = "";
    const chunks = [];
    for (const seg of inWindow) {
      const cleaned = seg.text.replace(/\s+/g, " ").trim();
      if (!cleaned) continue;
      if (fullText) fullText += " ";
      const charStart = fullText.length;
      fullText += cleaned;
      chunks.push({
        start: seg.start,
        charStart,
        charEnd: fullText.length,
      });
    }
    if (!fullText) return "";

    // Account for ~1s human pause reaction delay when locating the active line
    const anchorSec = Math.max(0, targetSec - 1);
    let anchorChunk = chunks[0];
    for (const chunk of chunks) {
      if (chunk.start <= anchorSec) {
        anchorChunk = chunk;
      } else {
        break;
      }
    }
    const anchorChar = Math.floor((anchorChunk.charStart + anchorChunk.charEnd) / 2);

    // Split into sentence spans on . ! ? boundaries
    const sentenceSpans = [];
    const regex = /[^.!?]+(?:[.!?]+["'”’)\]]*|$)/g;
    let m;
    while ((m = regex.exec(fullText)) !== null) {
      const rawSpan = m[0];
      const leadTrim = rawSpan.length - rawSpan.trimStart().length;
      const text = rawSpan.trim();
      if (!text) continue;
      sentenceSpans.push({
        start: m.index + leadTrim,
        end: m.index + leadTrim + text.length,
        text,
      });
    }

    // Unpunctuated auto-captions fallback: take a focused ~18s window around targetSec
    const hasPunctuation = sentenceSpans.length > 1 || /[.!?]["'”’)\]]*$/.test(fullText);
    if (!hasPunctuation && fullText.length > 260) {
      const tight = inWindow
        .filter((s) => s.start >= Math.max(0, targetSec - 12) && s.start <= targetSec + 5)
        .map((s) => s.text.replace(/\s+/g, " ").trim())
        .filter(Boolean)
        .join(" ");
      return tight || fullText;
    }

    const needle = (targetWord || "").trim();
    if (needle) {
      const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const wordRe = new RegExp(`(?<!\\w)${escaped}(?!\\w)`, "i");
      const matching = sentenceSpans.filter((sp) => wordRe.test(sp.text));
      if (matching.length) {
        matching.sort((a, b) => {
          const distA = Math.abs((a.start + a.end) / 2 - anchorChar);
          const distB = Math.abs((b.start + b.end) / 2 - anchorChar);
          return distA - distB;
        });
        return matching[0].text;
      }
    }

    const containing = sentenceSpans.find(
      (sp) => anchorChar >= sp.start && anchorChar <= sp.end
    );
    if (containing) return containing.text;

    sentenceSpans.sort((a, b) => {
      const distA = Math.abs((a.start + a.end) / 2 - anchorChar);
      const distB = Math.abs((b.start + b.end) / 2 - anchorChar);
      return distA - distB;
    });
    return sentenceSpans[0] ? sentenceSpans[0].text : fullText;
  }

  function readTranscriptPanelSegments() {
    const nodes = document.querySelectorAll(
      "ytd-transcript-segment-renderer, transcript-segment-view-model"
    );
    if (!nodes.length) return [];
    const segments = [];
    for (const node of nodes) {
      const tsEl = node.querySelector(
        ".segment-timestamp, .ytwTranscriptSegmentViewModelTimestamp, [class*='Timestamp'], [class*='timestamp']"
      );
      const rawTs = tsEl ? tsEl.textContent : "";
      const start = parseTimestampText(rawTs);
      if (start === null) continue;

      const textEl = node.querySelector(
        "yt-formatted-string.segment-text, .segment-text, [class*='SegmentText'], span.yt-core-attributed-string"
      );
      let text = textEl ? textEl.textContent : "";
      if (!text) {
        const clone = node.cloneNode(true);
        clone
          .querySelectorAll(
            ".segment-timestamp, .ytwTranscriptSegmentViewModelTimestamp, [class*='Timestamp'], [class*='timestamp']"
          )
          .forEach((el) => el.remove());
        text = clone.textContent || "";
      }
      text = text.replace(/\s+/g, " ").trim();
      if (text) {
        segments.push({ start, text });
      }
    }
    return segments;
  }

  async function fetchTimedTextSegments() {
    const params = new URLSearchParams(window.location.search);
    const videoId = params.get("v") || "";
    const resources = performance.getEntriesByType("resource") || [];
    const timedTextEntries = resources.filter(
      (entry) =>
        typeof entry.name === "string" &&
        entry.name.includes("/api/timedtext") &&
        (!videoId || entry.name.includes("v=" + videoId))
    );
    if (!timedTextEntries.length) return [];

    const latestUrl = timedTextEntries[timedTextEntries.length - 1].name;
    try {
      const url = new URL(latestUrl);
      url.searchParams.set("fmt", "json3");
      const resp = await fetch(url.toString(), { credentials: "include" });
      if (!resp.ok) return [];
      const data = await resp.json();
      const events = Array.isArray(data && data.events) ? data.events : [];
      const segments = [];
      for (const ev of events) {
        if (!Array.isArray(ev.segs) || typeof ev.tStartMs !== "number") continue;
        const text = ev.segs
          .map((s) => (typeof s.utf8 === "string" ? s.utf8 : ""))
          .join("")
          .replace(/\s+/g, " ")
          .trim();
        if (text) {
          segments.push({ start: ev.tStartMs / 1000, text });
        }
      }
      return segments;
    } catch {
      return [];
    }
  }

  let word = "";
  let context = "";
  let timestampSeconds = null;
  let source = "";

  const selection = window.getSelection();
  const selectedText = selection ? selection.toString().trim() : "";
  let selectedTranscriptTs = null;

  if (selectedText) {
    if (selection.rangeCount > 0) {
      let selNode = selection.getRangeAt(0).commonAncestorContainer;
      if (selNode.nodeType === Node.TEXT_NODE) selNode = selNode.parentElement;
      const transcriptSeg =
        isYouTube && selNode && selNode.closest
          ? selNode.closest(
              "ytd-transcript-segment-renderer, transcript-segment-view-model"
            )
          : null;
      if (transcriptSeg) {
        const tsEl = transcriptSeg.querySelector(
          ".segment-timestamp, .ytwTranscriptSegmentViewModelTimestamp, [class*='Timestamp'], [class*='timestamp']"
        );
        selectedTranscriptTs = parseTimestampText(tsEl ? tsEl.textContent : "");
      }
    }

    if (selectedText.split(/\s+/).length <= 6) {
      word = selectedText;
      if (!isYouTube && selection.rangeCount > 0) {
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
          source = "selection";
        }
      }
    } else {
      context = selectedText.replace(/\s+/g, " ").trim();
      source = "selection";
    }
  }

  if (isYouTube) {
    const video =
      document.querySelector("#movie_player video.html5-main-video") ||
      document.querySelector("video");
    if (selectedTranscriptTs !== null) {
      timestampSeconds = selectedTranscriptTs;
    } else if (video && Number.isFinite(video.currentTime)) {
      timestampSeconds = Math.max(0, Math.floor(video.currentTime));
    }

    if (!context && timestampSeconds !== null) {
      const targetWord = word || hintWord;

      // Tier 1: Open YouTube Transcript panel DOM (instant, already punctuated)
      const panelSegments = readTranscriptPanelSegments();
      if (panelSegments.length) {
        context = extractSentenceFromSegments(
          panelSegments,
          timestampSeconds,
          targetWord
        );
        if (context) source = "transcript";
      }

      // Tier 2: Active player's /api/timedtext track (works even if Transcript panel is closed)
      if (!context) {
        const timedSegments = await fetchTimedTextSegments();
        if (timedSegments.length) {
          context = extractSentenceFromSegments(
            timedSegments,
            timestampSeconds,
            targetWord
          );
          if (context) source = "captions";
        }
      }

      // Tier 3: On-screen rolling caption overlay fallback
      if (!context) {
        const segments = Array.from(
          document.querySelectorAll(".ytp-caption-segment")
        )
          .map((el) => (el.textContent || "").trim())
          .filter(Boolean);
        if (segments.length) {
          context = segments.join(" ").replace(/\s+/g, " ").trim();
          source = "overlay";
        }
      }
    }
  }

  return {
    url: window.location.href,
    title: document.title || "",
    word,
    context,
    timestampSeconds,
    source,
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
    source: "",
  };
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractPageCapture,
      args: [fallbackSelection.trim()],
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
            args: [message.hintWord || ""],
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
