"use strict";

const API_BASE       = "http://localhost:5000";
const HIGH_RISK_RATIO = 0.8;
const FETCH_TIMEOUT_MS = 10_000;

// tabId → { url, loaded }
const pendingNav = new Map();

// URL → Promise<data> — deduplicates concurrent scans for the same URL
const inFlight = new Map();

// URLs that user has approved to proceed with (bypass warning)
const bypassedUrls = new Set();

// ---------------------------------------------------------------------------
// Message handler: content.js and popup.js send { action:"scan", url:"..." }
// ---------------------------------------------------------------------------
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === "scan") {
    fetchScan(msg.url)
      .then(data => sendResponse({ success: true, data }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true; // keep channel open for async response
  } else if (msg.action === "allowBypass") {
    bypassedUrls.add(msg.url);
    // Auto-remove after 3 seconds to prevent indefinite bypassing
    setTimeout(() => bypassedUrls.delete(msg.url), 3000);
    sendResponse({ success: true });
    return true;
  }
  return false;
});

// ---------------------------------------------------------------------------
// Navigation interception
// ---------------------------------------------------------------------------
chrome.webNavigation.onBeforeNavigate.addListener((details) => {
  if (details.frameId !== 0) return;
  const { tabId, url } = details;

  if (!url.startsWith("http://") && !url.startsWith("https://")) return;
  if (isLoopbackUrl(url)) return;

  // Check if user has approved this URL (via "Proceed Anyway")
  if (bypassedUrls.has(url)) {
    bypassedUrls.delete(url);
    pendingNav.delete(tabId);
    return;
  }

  pendingNav.set(tabId, { url, loaded: false });

  fetchScan(url)
    .then(data => {
      const entry = pendingNav.get(tabId);
      if (!entry || entry.url !== url) return; // user navigated away

      const { phishing_votes, total_models, verdict } = data.ensemble;

      if (verdict === "bad" && phishing_votes / total_models >= HIGH_RISK_RATIO) {
        const warnUrl =
          chrome.runtime.getURL("warning.html") +
          "?url="   + encodeURIComponent(url) +
          "&votes=" + encodeURIComponent(String(phishing_votes)) +
          "&total=" + encodeURIComponent(String(total_models));

        if (entry.loaded) {
          // Page loaded before scan returned — inject overlay
          chrome.tabs.sendMessage(tabId, {
            action: "showWarning",
            url,
            votes: phishing_votes,
            total: total_models,
          }).catch(() => {});
        } else {
          // Redirect before the phishing page renders
          chrome.tabs.update(tabId, { url: warnUrl }).catch(() => {});
        }
      }

      pendingNav.delete(tabId);
    })
    .catch(() => {
      pendingNav.delete(tabId);
    });
});

chrome.webNavigation.onCompleted.addListener((details) => {
  if (details.frameId !== 0) return;
  const entry = pendingNav.get(details.tabId);
  if (entry) entry.loaded = true;
});

chrome.webNavigation.onErrorOccurred.addListener((details) => {
  pendingNav.delete(details.tabId);
});

// B3 fix: clean up Map when a tab is closed to prevent unbounded growth
chrome.tabs.onRemoved.addListener((tabId) => {
  pendingNav.delete(tabId);
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// B12 fix: catch all loopback variants, not just "localhost:5000"
function isLoopbackUrl(url) {
  try {
    const { hostname } = new URL(url);
    return (
      hostname === "localhost" ||
      hostname === "127.0.0.1" ||
      hostname === "[::1]"
    );
  } catch {
    return false;
  }
}

// B4 fix: AbortController timeout so a hung Flask server doesn't stall the SW.
// B14 fix: inFlight Map deduplicates concurrent scans for the same URL.
async function fetchScan(url) {
  if (inFlight.has(url)) return inFlight.get(url);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  const promise = fetch(`${API_BASE}/api/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, include_quantum: false }),
    signal: controller.signal,
    credentials: "include",
  })
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .finally(() => {
      clearTimeout(timer);
      inFlight.delete(url);
    });

  inFlight.set(url, promise);
  return promise;
}
