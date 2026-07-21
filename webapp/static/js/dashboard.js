// PhishGuard — Analytics Dashboard page

(function () {
  const escHtml = window.PhishGuard.escHtml;
  if (!document.getElementById("dashCards")) return;  // not on dashboard page

  const THESIS_ACCURACY = [
    { label: "Naive Bayes",         acc: 96.98, type: "classical" },
    { label: "Logistic Regression", acc: 92.49, type: "classical" },
    { label: "MLP Neural Net",      acc: 92.32, type: "classical" },
    { label: "KNN (k=3)",           acc: 91.86, type: "classical" },
    { label: "Random Forest",       acc: 91.66, type: "classical" },
    { label: "SVM",                 acc: 90.37, type: "classical" },
    { label: "VQC ⚛️",  acc: 79.50, type: "quantum" },
    { label: "QKNN ⚛️", acc: 77.80, type: "quantum" },
    { label: "QSVM ⚛️", acc: 76.90, type: "quantum" },
  ];

  const THESIS_SPEED = [
    { label: "Naive Bayes",    ms: 1,     type: "classical" },
    { label: "Logistic Reg.",  ms: 1,     type: "classical" },
    { label: "SVM",            ms: 2,     type: "classical" },
    { label: "MLP Neural Net", ms: 3,     type: "classical" },
    { label: "KNN (k=3)",      ms: 4,     type: "classical" },
    { label: "Random Forest",  ms: 7,     type: "classical" },
    { label: "VQC ⚛️",   ms: 420,   type: "quantum"   },
    { label: "QSVM ⚛️",  ms: 19000, type: "quantum"   },
    { label: "QKNN ⚛️",  ms: 28000, type: "quantum"   },
  ];

  let _charts = {};

  function destroyChart(key) {
    if (_charts[key]) { _charts[key].destroy(); delete _charts[key]; }
  }

  async function loadDashboard() {
    try {
      const [statsResp, histResp] = await Promise.all([
        fetch("/api/stats"),
        fetch("/api/history"),
      ]);
      const stats   = await statsResp.json();
      const history = await histResp.json();
      renderCards(stats);
      renderDailyChart(stats.daily_counts);
      renderSplitPie(stats.phishing, stats.safe);
      renderAccuracyChart();
      renderSpeedChart();
      renderTldChart(stats.top_tlds);
      renderHistory(history);
    } catch (err) {
      document.getElementById("dashCards").innerHTML =
        `<div class="col-12"><div class="alert alert-danger">Failed to load stats: ${escHtml(err.message)}</div></div>`;
    }
  }

  function renderCards(stats) {
    const cards = [
      { label: "Total Scanned",  value: stats.total.toLocaleString(),     color: "primary",   icon: "🔍" },
      { label: "Phishing Found", value: stats.phishing.toLocaleString(),  color: "danger",    icon: "⚠️" },
      { label: "Safe URLs",      value: stats.safe.toLocaleString(),      color: "success",   icon: "✅" },
      { label: "Risk Rate",      value: stats.phishing_pct + "%",         color: "warning",   icon: "📊" },
      { label: "Scanned Today",  value: stats.today.toLocaleString(),     color: "info",      icon: "📅" },
      { label: "Last 7 Days",    value: stats.this_week.toLocaleString(), color: "secondary", icon: "📆" },
    ];
    document.getElementById("dashCards").innerHTML = cards.map(c => `
      <div class="col-6 col-md-4 col-lg-2">
        <div class="card text-center border-${c.color} shadow-sm">
          <div class="card-body py-3">
            <div class="dash-card-icon">${c.icon}</div>
            <div class="fs-4 fw-bold text-${c.color}">${c.value}</div>
            <div class="text-muted small">${c.label}</div>
          </div>
        </div>
      </div>`).join("");
  }

  function renderDailyChart(dailyCounts) {
    destroyChart("daily");
    const today = new Date();
    const labels = [], totalData = [], phishingData = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const dateStr = d.toISOString().slice(0, 10);
      const found   = dailyCounts.find(r => r.date === dateStr);
      labels.push(dateStr.slice(5));
      totalData.push(found ? found.total    : 0);
      phishingData.push(found ? found.phishing : 0);
    }
    _charts.daily = new Chart(
      document.getElementById("dailyChart").getContext("2d"), {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Total scans",
              data: totalData,
              borderColor: "#0d6efd",
              backgroundColor: "#0d6efd22",
              fill: true,
              tension: 0.3,
            },
            {
              label: "Phishing",
              data: phishingData,
              borderColor: "#dc3545",
              backgroundColor: "#dc354522",
              fill: true,
              tension: 0.3,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: "top" } },
          scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
        },
      }
    );
  }

  function renderSplitPie(phishing, safe) {
    destroyChart("pie");
    _charts.pie = new Chart(
      document.getElementById("splitPieChart").getContext("2d"), {
        type: "doughnut",
        data: {
          labels: ["Safe", "Phishing"],
          datasets: [{
            data: [safe, phishing],
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
      }
    );
  }

  function renderAccuracyChart() {
    destroyChart("accuracy");
    const colors = THESIS_ACCURACY.map(m =>
      m.type === "quantum" ? "#6f42c1" : "#0d6efd"
    );
    _charts.accuracy = new Chart(
      document.getElementById("accuracyChart").getContext("2d"), {
        type: "bar",
        data: {
          labels: THESIS_ACCURACY.map(m => m.label),
          datasets: [{
            label: "Accuracy (%)",
            data: THESIS_ACCURACY.map(m => m.acc),
            backgroundColor: colors.map(c => c + "cc"),
            borderColor: colors,
            borderWidth: 1,
          }],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: {
              min: 70,
              max: 100,
              ticks: { callback: v => v + "%" },
            },
          },
        },
      }
    );
  }

  function renderSpeedChart() {
    destroyChart("speed");
    const colors = THESIS_SPEED.map(m =>
      m.type === "quantum" ? "#6f42c1cc" : "#198754cc"
    );
    _charts.speed = new Chart(
      document.getElementById("speedChart").getContext("2d"), {
        type: "bar",
        data: {
          labels: THESIS_SPEED.map(m => m.label),
          datasets: [{
            label: "Prediction time",
            data: THESIS_SPEED.map(m => m.ms),
            backgroundColor: colors,
            borderColor: colors.map(c => c.slice(0, 7)),
            borderWidth: 1,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: ctx => {
                  const ms = ctx.raw;
                  return " " + (ms >= 1000 ? (ms / 1000).toFixed(1) + " s" : ms + " ms");
                },
              },
            },
          },
          scales: {
            y: {
              type: "logarithmic",
              ticks: {
                callback: v => {
                  if (v >= 1000) return (v / 1000) + "s";
                  if (v >= 1)    return v + "ms";
                  return null;
                },
              },
            },
          },
        },
      }
    );
  }

  function renderTldChart(topTlds) {
    destroyChart("tld");
    if (!topTlds || !topTlds.length) {
      document.getElementById("tldEmpty").classList.remove("d-none");
      return;
    }
    document.getElementById("tldEmpty").classList.add("d-none");
    _charts.tld = new Chart(
      document.getElementById("tldChart").getContext("2d"), {
        type: "bar",
        data: {
          labels: topTlds.map(t => t.tld),
          datasets: [{
            label: "Occurrences",
            data: topTlds.map(t => t.count),
            backgroundColor: "#fd7e1499",
            borderColor: "#fd7e14",
            borderWidth: 1,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
        },
      }
    );
  }

  function renderHistory(history) {
    if (!history.length) {
      document.getElementById("historyTableBody").innerHTML =
        '<tr><td colspan="5" class="text-center text-muted">No scans yet.</td></tr>';
      return;
    }
    document.getElementById("historyTableBody").innerHTML = history.map((r, i) => {
      const bad      = r.verdict === "bad";
      const conf     = r.confidence != null ? (r.confidence * 100).toFixed(1) + "%" : "—";
      const urlShort = r.url.length > 65 ? r.url.slice(0, 62) + "…" : r.url;
      const ts       = r.timestamp ? r.timestamp.slice(0, 16).replace("T", " ") : "—";
      return `
        <tr>
          <td class="text-muted">${i + 1}</td>
          <td class="font-monospace small" title="${escHtml(r.url)}">${escHtml(urlShort)}</td>
          <td><span class="badge ${bad ? "bg-danger" : "bg-success"}">${bad ? "Phishing" : "Safe"}</span></td>
          <td>${conf}</td>
          <td class="text-muted small">${ts}</td>
        </tr>`;
    }).join("");
  }

  async function clearHistory() {
    const confirmed = confirm("⚠️ This will permanently delete all your scan history. This cannot be undone. Continue?");
    if (!confirmed) return;

    document.getElementById("dashResetBtn").disabled = true;
    try {
      const resp = await fetch("/api/clear-history", { method: "POST" });
      const data = await resp.json();

      if (resp.ok && data.success) {
        alert(`✓ History cleared! Deleted ${data.deleted} records.`);
        loadDashboard();
      } else {
        alert(`Error: ${data.error || "Failed to clear history"}`);
      }
    } catch (err) {
      alert(`Error: ${escHtml(err.message)}`);
    } finally {
      document.getElementById("dashResetBtn").disabled = false;
    }
  }

  loadDashboard();
  document.getElementById("dashRefreshBtn").addEventListener("click", loadDashboard);
  document.getElementById("dashResetBtn").addEventListener("click", clearHistory);
})();
