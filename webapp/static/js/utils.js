// PhishGuard — shared utilities loaded on every page before page-specific scripts.

window.PhishGuard = window.PhishGuard || {};

/**
 * Escape a string for safe insertion into HTML.
 * Handles &, <, >, ", and ' so it is safe in both element content and attributes.
 */
window.PhishGuard.escHtml = function (str) {
  return String(str)
    .replace(/&/g,  "&amp;")
    .replace(/</g,  "&lt;")
    .replace(/>/g,  "&gt;")
    .replace(/"/g,  "&quot;")
    .replace(/'/g,  "&#39;");
};
