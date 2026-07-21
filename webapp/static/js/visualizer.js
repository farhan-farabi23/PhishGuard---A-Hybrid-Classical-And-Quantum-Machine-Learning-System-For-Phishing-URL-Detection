// PhishGuard — Quantum Circuit Visualizer page

(function () {
  const vizBtn = document.getElementById("vizBtn");
  if (!vizBtn) return;  // not on the visualizer page

  let _angleChart = null;
  let _running = false;
  const vizError = document.getElementById("vizError");

  function showError(msg) {
    if (!vizError) return;
    vizError.textContent = msg;
    vizError.classList.remove("d-none");
  }
  function clearError() {
    if (!vizError) return;
    vizError.classList.add("d-none");
    vizError.textContent = "";
  }

  vizBtn.addEventListener("click", runVisualize);
  document.getElementById("vizUrlInput").addEventListener("keydown", e => {
    if (e.key === "Enter") runVisualize();
  });

  async function runVisualize() {
    if (_running) return;
    const url = document.getElementById("vizUrlInput").value.trim();
    if (!url) {
      document.getElementById("vizUrlInput").classList.add("is-invalid");
      return;
    }
    document.getElementById("vizUrlInput").classList.remove("is-invalid");
    clearError();

    _running = true;
    document.getElementById("vizSpinner").classList.remove("d-none");
    document.getElementById("vizResults").classList.add("d-none");
    vizBtn.disabled = true;

    try {
      const resp = await fetch("/api/circuit?url=" + encodeURIComponent(url));
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || resp.status);
      renderVisualizer(data);
    } catch (err) {
      showError("Error: " + err.message);
    } finally {
      _running = false;
      document.getElementById("vizSpinner").classList.add("d-none");
      vizBtn.disabled = false;
    }
  }

  function renderVisualizer(data) {
    const { angles, n_qubits, n_layers } = data;
    const PI = Math.PI;

    // Show the results section FIRST so the chart container has real pixel
    // dimensions when Chart.js measures it. Creating a chart while the
    // ancestor has d-none gives 0×0 dimensions; the ResizeObserver then
    // fires repeatedly as content below (circuit table, pipeline steps)
    // causes the h-100 card to grow, causing the continuous-increase blink.
    const vizResults = document.getElementById("vizResults");
    vizResults.classList.remove("d-none");
    // Force a synchronous layout reflow so the browser assigns correct pixel
    // dimensions to the chart container before Chart.js reads them.
    // eslint-disable-next-line no-unused-expressions
    void vizResults.offsetHeight;

    // Render 3D visualization
    if (window.render3DVisualization) {
      window.render3DVisualization(angles);
    }

    // Angle bar chart — coloured by value (blue=low, green=mid, red=high)
    if (_angleChart) _angleChart.destroy();
    const angleColors = angles.map(a => {
      const ratio = a / PI;
      const hue = Math.round((1 - ratio) * 220);
      return `hsl(${hue}, 70%, 55%)`;
    });
    _angleChart = new Chart(document.getElementById("angleChart").getContext("2d"), {
      type: "bar",
      data: {
        labels: angles.map((_, i) => `θ${i}  (qubit ${i})`),
        datasets: [{
          label: "Angle (rad)",
          data: angles,
          backgroundColor: angleColors,
          borderColor: angleColors.map(c => c.replace("55%", "38%")),
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            min: 0,
            max: parseFloat(PI.toFixed(4)),
            ticks: {
              callback: v => {
                if (Math.abs(v) < 0.01)        return "0";
                if (Math.abs(v - PI / 2) < 0.05) return "π/2";
                if (Math.abs(v - PI) < 0.05)    return "π";
                return v.toFixed(2);
              },
            },
          },
        },
      },
    });

    // Circuit diagram table
    renderCircuitDiagram(angles, n_qubits, n_layers);

    // Angle parameter table
    document.getElementById("angleTableBody").innerHTML = angles.map((a, i) => `
      <tr>
        <td class="fw-bold">q${i}</td>
        <td><code>${a.toFixed(4)}</code></td>
        <td>${(a * 180 / PI).toFixed(2)}°</td>
        <td><code>RY(${a.toFixed(3)})</code></td>
        <td class="text-muted small">PCA component ${i} rescaled to [0, π]</td>
      </tr>`).join("");

    // Pipeline step cards
    const steps = [
      {
        icon: "🔗",
        title: "TF-IDF (50k features)",
        text: "The URL is tokenised and stemmed. Term-frequency × inverse-document-frequency scores are computed across a 50,000-word vocabulary, capturing which URL tokens are unusual vs. common.",
      },
      {
        icon: "📐",
        title: "SVD-50 + 6 URL features",
        text: "Truncated SVD reduces the TF-IDF vector to 50 latent dimensions. Six hand-crafted features are appended: URL length, dot count, digit count, special characters, IP flag, and subdomain depth.",
      },
      {
        icon: "📏",
        title: "StandardScaler",
        text: "All 56 features are zero-mean, unit-variance normalised so that scale differences between TF-IDF dimensions and raw counts do not bias the model.",
      },
      {
        icon: "🔭",
        title: `PCA → ${n_qubits} components`,
        text: `Principal Component Analysis projects the 56-dim vector onto the ${n_qubits} directions of maximum variance — one per qubit. This is the dimensionality that fits in the quantum circuit.`,
      },
      {
        icon: "📡",
        title: "MinMaxScaler → [0, π]",
        text: `Each PCA component is rescaled to the range [0, π]. This is the valid input range for quantum RY rotation gates. The values shown in the bar chart above are these final angles.`,
      },
      {
        icon: "⚛️",
        title: `VQC (${n_layers} layers)`,
        text: `AngleEmbedding applies RY(θᵢ) to qubit i, encoding the URL into a quantum state. Then ${n_layers} variational layers of RY+RZ rotations + a CNOT ring entangle the qubits. Pauli-Z measurements give expectation values used for classification.`,
      },
    ];
    document.getElementById("pipelineSteps").innerHTML = steps.map(s => `
      <div class="col-12 col-md-6 col-xl-4 mb-3">
        <div class="d-flex gap-3 align-items-start">
          <div class="fs-2 flex-shrink-0">${s.icon}</div>
          <div>
            <div class="fw-semibold">${s.title}</div>
            <div class="text-muted small">${s.text}</div>
          </div>
        </div>
      </div>`).join("");

  }

  function renderCircuitDiagram(angles, n_qubits, n_layers) {
    const PI = Math.PI;
    const rows = [];

    rows.push('<div class="table-responsive">');
    rows.push('<table class="table table-bordered table-sm text-center align-middle mb-0" style="font-size:0.8rem">');
    rows.push("<thead class='table-dark'><tr>");
    rows.push('<th class="text-start ps-2">Qubit</th>');
    rows.push('<th>AngleEmbedding<br><small class="fw-normal opacity-75">RY(θᵢ)</small></th>');
    for (let l = 0; l < n_layers; l++) {
      rows.push(`<th>Layer ${l + 1}<br><small class="fw-normal opacity-75">RY · RZ · CNOT</small></th>`);
    }
    rows.push('<th>Measure<br><small class="fw-normal opacity-75">⟨Z⟩</small></th>');
    rows.push("</tr></thead><tbody>");

    for (let q = 0; q < n_qubits; q++) {
      const angle = angles[q] || 0;
      const ratio = angle / PI;
      const hue = Math.round((1 - ratio) * 220);
      const colorStyle = `background:hsl(${hue},65%,45%);color:#fff`;

      rows.push("<tr>");
      rows.push(`<td class="text-start ps-2 fw-bold">q${q}</td>`);
      rows.push(`<td><span class="badge" style="${colorStyle}">RY(${angle.toFixed(2)})</span></td>`);

      for (let l = 0; l < n_layers; l++) {
        const ctrlQ = (q + n_qubits - 1) % n_qubits;
        const tgtQ  = (q + 1) % n_qubits;
        rows.push(`<td>
          <span class="badge bg-secondary me-1">RY</span>
          <span class="badge bg-secondary me-1">RZ</span>
          <span class="badge bg-primary" title="CNOT ctrl=q${ctrlQ} target=q${tgtQ}">CNOT</span>
        </td>`);
      }
      rows.push('<td><span class="badge bg-success">⟨Z⟩</span></td>');
      rows.push("</tr>");
    }

    rows.push("</tbody></table></div>");
    document.getElementById("circuitDiagram").innerHTML = rows.join("");
  }
})();
