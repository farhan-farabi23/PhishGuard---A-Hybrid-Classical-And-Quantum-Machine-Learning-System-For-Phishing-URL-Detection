// PhishGuard — URL Analyser page

document.addEventListener("DOMContentLoaded", () => {
  const escHtml      = window.PhishGuard.escHtml;
  const scanBtn      = document.getElementById("scanBtn");
  const urlInput     = document.getElementById("urlInput");
  const quantumToggle = document.getElementById("quantumToggle");
  const scanError    = document.getElementById("scanError");

  if (!scanBtn) return;  // not on the analyser page

  let _scanning = false;

  function showError(msg) {
    if (!scanError) return;
    scanError.textContent = msg;
    scanError.classList.remove("d-none");
  }
  function clearError() {
    if (!scanError) return;
    scanError.classList.add("d-none");
    scanError.textContent = "";
  }

  // Pre-fill URL from ?url= query parameter (used by the browser extension link)
  const _prefilledUrl = new URLSearchParams(window.location.search).get("url");
  if (_prefilledUrl) {
    urlInput.value = _prefilledUrl;
    runScan();
  }

  scanBtn.addEventListener("click", runScan);
  urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") runScan(); });

  async function runScan() {
    if (_scanning) return;
    const url = urlInput.value.trim();
    if (!url) { urlInput.classList.add("is-invalid"); return; }
    urlInput.classList.remove("is-invalid");
    clearError();

    _scanning = true;
    setSpinner(true, quantumToggle.checked
      ? "Running all 9 models… quantum models may take ~30 seconds."
      : "Running 6 classical models…");

    try {
      const resp = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, include_quantum: quantumToggle.checked }),
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || `Server error: ${resp.status}`);
      }
      const data = await resp.json();
      renderResults(data);
    } catch (err) {
      showError("Scan failed: " + err.message);
    } finally {
      _scanning = false;
      setSpinner(false);
    }
  }

  function setSpinner(show, msg = "") {
    document.getElementById("scanSpinner").classList.toggle("d-none", !show);
    if (show) document.getElementById("resultsSection").classList.add("d-none");
    document.getElementById("spinnerMsg").textContent = msg;
    scanBtn.disabled = show;
  }

  function renderResults(data) {
    // Verdict banner
    const isPhishing = data.ensemble.verdict === "bad";
    const banner = document.getElementById("verdictBanner");
    banner.className = "verdict-banner mb-4 p-4 rounded text-white text-center " +
      (isPhishing ? "bg-danger" : "bg-success");
    document.getElementById("verdictIcon").textContent = isPhishing ? "⚠️" : "✅";
    document.getElementById("verdictText").textContent = isPhishing ? "PHISHING DETECTED" : "SAFE URL";
    document.getElementById("verdictSub").textContent  =
      `${data.ensemble.phishing_votes} of ${data.ensemble.total_models} models flagged this URL`;

    // URL Dissector
    renderDissector(data.meta.url, data.url_features);

    // Feature panel
    const feats = data.url_features;
    const featureRows = [
      { label: "Length",          value: feats.length,          warn: feats.length > 75 },
      { label: "Dot count",       value: feats.dots,            warn: feats.dots > 3 },
      { label: "Digit count",     value: feats.digits,          warn: feats.digits > 5 },
      { label: "Special chars",   value: feats.special_chars,   warn: feats.special_chars > 4 },
      { label: "IP address",      value: feats.has_ip ? "Yes" : "No", warn: !!feats.has_ip },
      { label: "Subdomain depth", value: feats.subdomain_depth, warn: feats.subdomain_depth > 1 },
    ];
    document.getElementById("featureList").innerHTML = featureRows.map(r => `
      <li class="list-group-item d-flex justify-content-between align-items-center">
        <span>${r.label}</span>
        <span>${r.value} ${r.warn ? "⚠️" : "✅"}</span>
      </li>`).join("");

    // Model table
    const MODEL_META = {
      knn:    { name: "KNN (k=3)",           type: "Classical" },
      logreg: { name: "Logistic Regression", type: "Classical" },
      nb:     { name: "Naive Bayes",          type: "Classical" },
      svm:    { name: "SVM",                 type: "Classical" },
      rf:     { name: "Random Forest",        type: "Classical" },
      mlp:    { name: "MLP Neural Net",       type: "Classical" },
      vqc:    { name: "VQC ⚛️",              type: "Quantum"   },
      qknn:   { name: "QKNN ⚛️",             type: "Quantum"   },
      qsvm:   { name: "QSVM ⚛️",             type: "Quantum"   },
    };
    const ORDER = ["nb", "logreg", "mlp", "knn", "rf", "svm", "vqc", "qknn", "qsvm"];

    const rows = ORDER.map(key => {
      const m    = data[key];
      const meta = MODEL_META[key];
      if (!m) return `
        <tr class="text-muted">
          <td>${meta.name}</td>
          <td><span class="badge bg-secondary">${meta.type}</span></td>
          <td colspan="3" class="fst-italic">skipped</td>
        </tr>`;
      const bad     = m.verdict === "bad";
      const conf    = (m.confidence * 100).toFixed(1);
      const timeStr = m.time_ms >= 1000
        ? (m.time_ms / 1000).toFixed(1) + "s"
        : m.time_ms + "ms";
      return `
        <tr>
          <td>${meta.name}</td>
          <td><span class="badge ${meta.type === "Quantum" ? "bg-purple" : "bg-secondary"}">${meta.type}</span></td>
          <td><span class="badge ${bad ? "bg-danger" : "bg-success"}">${bad ? "Phishing" : "Safe"}</span></td>
          <td>
            <div class="progress" style="height:6px;min-width:80px"
                 role="progressbar"
                 aria-valuenow="${conf}" aria-valuemin="0" aria-valuemax="100"
                 aria-label="${meta.name} confidence ${conf}%">
              <div class="progress-bar ${bad ? "bg-danger" : "bg-success"}"
                   style="width:${conf}%"></div>
            </div>
            <small class="text-muted">${conf}%</small>
          </td>
          <td class="text-muted small">${timeStr}</td>
        </tr>`;
    }).join("");

    document.getElementById("modelTableBody").innerHTML = rows;

    // Ensemble footer row
    const ensemblePhishing = data.ensemble.verdict === "bad";
    const ensembleConf = data.ensemble.confidence
      ? ` · ${(data.ensemble.confidence * 100).toFixed(1)}% avg confidence`
      : "";
    document.getElementById("modelTableFoot").innerHTML = `
      <tr>
        <td colspan="2">Ensemble (majority vote)</td>
        <td><span class="badge ${ensemblePhishing ? "bg-danger" : "bg-success"} fs-6">
          ${ensemblePhishing ? "PHISHING" : "SAFE"}
        </span></td>
        <td>${data.ensemble.phishing_votes}/${data.ensemble.total_models} models${ensembleConf}</td>
        <td>—</td>
      </tr>`;

    document.getElementById("resultsSection").classList.remove("d-none");
  }

  function renderDissector(url, features) {
    const PHISHING_KEYWORDS = [
      "login", "secure", "paypal", "bank", "account", "verify", "update",
      "signin", "ebay", "amazon", "apple", "microsoft", "confirm", "password",
    ];
    const BAD_TLDS = [".xyz", ".tk", ".ml", ".ga", ".cf", ".gq", ".top", ".click", ".link", ".pw"];

    let html = "";
    const reasons = [];

    let protocol = "", rest = url;
    const protoMatch = url.match(/^(https?:\/\/)/i);
    if (protoMatch) {
      protocol = protoMatch[1];
      rest = url.slice(protocol.length);
    }

    const slashIdx  = rest.indexOf("/");
    const host      = slashIdx >= 0 ? rest.slice(0, slashIdx) : rest;
    const path      = slashIdx >= 0 ? rest.slice(slashIdx) : "";
    const hostParts = host.split(".");
    const tld       = hostParts.length > 1 ? "." + hostParts[hostParts.length - 1] : "";
    const domain    = hostParts.length > 1 ? hostParts[hostParts.length - 2] : host;
    const subdomains = hostParts.slice(0, hostParts.length - 2);

    const span = (text, cls, title = "") =>
      `<span class="url-part ${cls}" title="${escHtml(title)}">${escHtml(text)}</span>`;

    if (protocol) {
      const protoClass = protocol.startsWith("https") ? "url-safe" : "url-warn";
      html += span(protocol, protoClass, protocol.startsWith("https") ? "Encrypted connection" : "Unencrypted — HTTP");
      if (!protocol.startsWith("https")) reasons.push("Uses unencrypted HTTP");
    }

    subdomains.forEach(sub => {
      const hasBadKw = PHISHING_KEYWORDS.some(kw => sub.toLowerCase().includes(kw));
      html += span(sub + ".", hasBadKw ? "url-danger" : "url-neutral",
        hasBadKw ? `Suspicious keyword: "${sub}"` : "Subdomain");
      if (hasBadKw) reasons.push(`Suspicious keyword in subdomain: "${sub}"`);
    });

    const domainClass = features.has_ip ? "url-danger" : "url-neutral";
    html += span(domain, domainClass, features.has_ip ? "IP address instead of domain name" : "Domain");
    if (features.has_ip) reasons.push("Uses IP address instead of a domain name");

    const tldBad = BAD_TLDS.includes(tld.toLowerCase());
    if (tld) {
      html += span(tld, tldBad ? "url-danger" : "url-neutral", tldBad ? "High-risk TLD" : "TLD");
      if (tldBad) reasons.push(`High-risk top-level domain: "${tld}"`);
    }

    if (path) {
      const pathBad = PHISHING_KEYWORDS.some(kw => path.toLowerCase().includes(kw));
      html += span(path, pathBad ? "url-warn" : "url-neutral", pathBad ? "Suspicious path" : "Path");
      if (pathBad) reasons.push("Suspicious keywords in URL path");
    }

    if (features.length > 75) reasons.push(`Unusually long URL (${features.length} characters)`);
    if (features.dots > 3)    reasons.push(`High dot count (${features.dots}) — possible subdomain abuse`);

    document.getElementById("urlDissector").innerHTML = html;
    document.getElementById("suspicionReasons").innerHTML = reasons.length
      ? "⚠️ " + reasons.join(" &nbsp;·&nbsp; ⚠️ ")
      : "✅ No obvious structural issues found.";
  }
});
