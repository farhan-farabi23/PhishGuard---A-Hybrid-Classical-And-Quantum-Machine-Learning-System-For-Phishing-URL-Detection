"use strict";

// B1+B2 fix: extracted from inline <script> (blocked by MV3 CSP).
// B2 fix: buttons wired with addEventListener instead of onclick="..." attributes.
(function () {
  const p     = new URLSearchParams(window.location.search);
  const url   = p.get("url")   || "Unknown URL";
  const votes = parseInt(p.get("votes") || "0", 10);
  const total = parseInt(p.get("total") || "6",  10);
  const pct   = total > 0 ? Math.round(votes / total * 100) : 0;

  document.getElementById("stat-url").textContent   = url;
  document.getElementById("stat-votes").textContent = votes;
  document.getElementById("stat-total").textContent = total;
  document.getElementById("stat-pct").textContent   = pct + "%";

  document.getElementById("btn-back").addEventListener("click", function () {
    if (window.history.length > 1) {
      window.history.back();
    }
    // If there is no history (direct navigation to phishing URL), do nothing —
    // the browser's back button is also disabled in this state.
  });

  document.getElementById("btn-proceed").addEventListener("click", function () {
    // Validate scheme to prevent javascript: XSS via crafted query string
    if (/^https?:\/\//i.test(url)) {
      // Tell background.js to allow this URL, then navigate
      chrome.runtime.sendMessage({ action: "allowBypass", url: url }, () => {
        window.location.href = url;
      });
    }
  });
})();
