// PhishGuard — Batch Scanner page

(function () {
  const escHtml   = window.PhishGuard.escHtml;
  const batchBtn  = document.getElementById("batchBtn");
  if (!batchBtn) return;  // not on the batch page

  let _pieChart = null;
  let _barChart = null;

  const batchError = document.getElementById("batchError");
  function showError(msg) {
    if (!batchError) return;
    batchError.textContent = msg;
    batchError.classList.remove("d-none");
  }
  function clearError() {
    if (!batchError) return;
    batchError.classList.add("d-none");
    batchError.textContent = "";
  }

  batchBtn.addEventListener("click", runBatch);

  async function runBatch() {
    const fileInput = document.getElementById("batchFile");
    const maxUrls   = parseInt(document.getElementById("batchMax").value) || 200;

    if (!fileInput.files.length) {
      fileInput.classList.add("is-invalid");
      return;
    }
    fileInput.classList.remove("is-invalid");
    clearError();

    setBatchSpinner(true, `Scanning up to ${maxUrls} URLs — please wait…`);

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    formData.append("max_urls", maxUrls);

    try {
      const resp = await fetch("/api/batch", { method: "POST", body: formData });
      const data = await resp.json();
      if (!resp.ok) { showError("Error: " + (data.error || resp.status)); return; }
      renderBatchResults(data);
    } catch (err) {
      showError("Batch scan failed: " + err.message);
    } finally {
      setBatchSpinner(false);
    }
  }

  function setBatchSpinner(show, msg = "") {
    document.getElementById("batchSpinner").classList.toggle("d-none", !show);
    if (show) document.getElementById("batchResults").classList.add("d-none");
    document.getElementById("batchSpinnerMsg").textContent = msg;
    batchBtn.disabled = show;
  }

  function renderBatchResults(data) {
    // Show the results section first so chart containers have real pixel
    // dimensions before Chart.js measures them (same fix as visualizer).
    const batchResultsEl = document.getElementById("batchResults");
    batchResultsEl.classList.remove("d-none");
    void batchResultsEl.offsetHeight; // force synchronous layout reflow

    // Summary cards
    const cards = [
      { label: "Total Scanned", value: data.total,              color: "primary",  icon: "🔍" },
      { label: "Phishing",      value: data.phishing,           color: "danger",   icon: "⚠️" },
      { label: "Safe",          value: data.safe,               color: "success",  icon: "✅" },
      { label: "Risk Rate",     value: data.phishing_pct + "%", color: "warning",  icon: "📊" },
    ];
    document.getElementById("summaryCards").innerHTML = cards.map(c => `
      <div class="col-6 col-md-3">
        <div class="card text-center border-${c.color} shadow-sm">
          <div class="card-body py-3">
            <div class="fs-2">${c.icon}</div>
            <div class="fs-3 fw-bold text-${c.color}">${c.value}</div>
            <div class="text-muted small">${c.label}</div>
          </div>
        </div>
      </div>`).join("");

    // Doughnut chart
    if (_pieChart) _pieChart.destroy();
    const pieCtx = document.getElementById("pieChart").getContext("2d");
    _pieChart = new Chart(pieCtx, {
      type: "doughnut",
      data: {
        labels: ["Safe", "Phishing"],
        datasets: [{
          data: [data.safe, data.phishing],
          backgroundColor: ["#198754", "#dc3545"],
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom" } },
        cutout: "60%",
      },
    });

    // Per-model phishing bar chart
    const MODEL_LABELS = {
      nb: "Naive Bayes", logreg: "Log. Reg.", knn: "KNN",
      rf: "Rand. Forest", svm: "SVM", mlp: "MLP",
    };
    const barKeys   = Object.keys(data.model_counts);
    const barLabels = barKeys.map(k => MODEL_LABELS[k] || k);
    const barValues = barKeys.map(k => data.model_counts[k]);

    if (_barChart) _barChart.destroy();
    const barCtx = document.getElementById("barChart").getContext("2d");
    _barChart = new Chart(barCtx, {
      type: "bar",
      data: {
        labels: barLabels,
        datasets: [{
          label: "Phishing URLs detected",
          data: barValues,
          backgroundColor: "#dc3545aa",
          borderColor: "#dc3545",
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, max: data.total, ticks: { stepSize: 1 } },
        },
      },
    });

    // Top TLDs
    const tldHtml = data.top_tlds.map(t =>
      `<span class="badge bg-secondary me-2 mb-1" style="font-size:0.85rem">${escHtml(t.tld)} <span class="badge bg-light text-dark ms-1">${t.count}</span></span>`
    ).join("") || "<span class='text-muted'>No TLD data</span>";
    document.getElementById("tldBadges").innerHTML = tldHtml;

    // Results table
    document.getElementById("batchTableBody").innerHTML = data.results.map((r, i) => {
      const bad     = r.verdict === "bad";
      const conf    = typeof r.confidence === "number" ? (r.confidence * 100).toFixed(1) : "—";
      const urlShort = r.url.length > 70 ? r.url.slice(0, 67) + "…" : r.url;
      return `
        <tr class="${bad ? "table-danger-subtle" : ""}">
          <td class="text-muted">${i + 1}</td>
          <td class="font-monospace small" title="${escHtml(r.url)}">${escHtml(urlShort)}</td>
          <td><span class="badge ${bad ? "bg-danger" : "bg-success"}">${bad ? "Phishing" : "Safe"}</span></td>
          <td>${conf}%</td>
          <td>${r.phishing_votes}/${r.total_models}</td>
        </tr>`;
    }).join("");

    // Download button
    document.getElementById("downloadBtn").onclick = () => downloadCSV(data.results);
  }

  function downloadCSV(results) {
    const MODEL_ORDER = ["knn", "logreg", "nb", "svm", "rf", "mlp"];
    const MODEL_LABELS = {
      knn: "KNN", logreg: "LogisticRegression", nb: "NaiveBayes",
      svm: "SVM", rf: "RandomForest", mlp: "MLP",
    };

    // Build header with model columns
    const baseHeaders = ["index", "url", "ensemble_verdict", "ensemble_confidence_pct", "phishing_votes", "total_models"];
    const modelHeaders = [];
    for (const model of MODEL_ORDER) {
      modelHeaders.push(`${model}_verdict`);
      modelHeaders.push(`${model}_confidence_pct`);
    }
    const header = [...baseHeaders, ...modelHeaders].join(",") + "\n";

    // Build rows with model predictions
    const rows = results.map((r, i) => {
      const baseCols = [
        i + 1,
        `"${r.url.replace(/"/g, '""')}"`,
        r.verdict,
        (r.confidence * 100).toFixed(1),
        r.phishing_votes,
        r.total_models,
      ];

      const modelCols = [];
      const models = r.models || {};
      for (const model of MODEL_ORDER) {
        if (models[model]) {
          modelCols.push(models[model].verdict);
          modelCols.push((models[model].confidence * 100).toFixed(1));
        } else {
          modelCols.push("—");
          modelCols.push("—");
        }
      }

      return [...baseCols, ...modelCols].join(",");
    }).join("\n");

    const blob = new Blob([header + rows], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "security_report.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }
})();
