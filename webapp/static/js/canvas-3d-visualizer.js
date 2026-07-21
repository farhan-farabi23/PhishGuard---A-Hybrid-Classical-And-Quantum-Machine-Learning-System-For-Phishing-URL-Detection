// PhishGuard — Canvas-based 3D Quantum Circuit Visualizer (no external dependencies)

(function () {
  const container = document.getElementById("canvas3dContainer");
  if (!container) return;

  let canvas, ctx;
  let animationId = null;
  let isInitialized = false;

  // 3D visualization state
  const scene = {
    qubits: [],
    gates: [],
    camera: { x: 0, y: 0, z: 8 },
    rotation: { x: 0.3, y: 0.5, z: 0 },
    zoom: 0.1,
  };

  // Mouse interaction
  const mouse = {
    down: false,
    x: 0,
    y: 0,
    dx: 0,
    dy: 0,
  };

  const PI = Math.PI;
  const N_QUBITS = 4;
  const QUBIT_RADIUS = 0.5;
  const SCENE_RADIUS = 3;

  // 3D Vector and Matrix operations
  class Vec3 {
    constructor(x, y, z) {
      this.x = x;
      this.y = y;
      this.z = z;
    }
    rotateX(angle) {
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const y = this.y * cos - this.z * sin;
      const z = this.y * sin + this.z * cos;
      this.y = y;
      this.z = z;
      return this;
    }
    rotateY(angle) {
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const x = this.x * cos + this.z * sin;
      const z = -this.x * sin + this.z * cos;
      this.x = x;
      this.z = z;
      return this;
    }
    rotateZ(angle) {
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const x = this.x * cos - this.y * sin;
      const y = this.x * sin + this.y * cos;
      this.x = x;
      this.y = y;
      return this;
    }
    project(fov = 60) {
      const perspective = fov / (this.z + 8);
      return {
        x: this.x * perspective,
        y: this.y * perspective,
        z: this.z,
        depth: this.z,
      };
    }
    clone() {
      return new Vec3(this.x, this.y, this.z);
    }
  }

  function initCanvas() {
    // Clear container
    container.innerHTML = "";

    // Create canvas
    canvas = document.createElement("canvas");
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    container.appendChild(canvas);

    ctx = canvas.getContext("2d");
    if (!ctx) {
      container.innerHTML = '<div style="padding:30px;color:#ff6b6b;text-align:center;font-family:monospace;">Canvas 2D context not available</div>';
      return false;
    }

    // Set canvas resolution
    const width = container.offsetWidth || 800;
    const height = container.offsetHeight || 400;
    canvas.width = width * window.devicePixelRatio;
    canvas.height = height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    isInitialized = true;
    return true;
  }

  function createQubits(angles) {
    scene.qubits = [];
    for (let i = 0; i < N_QUBITS; i++) {
      const angle = angles[i] || 0;
      const ratio = Math.min(Math.max(angle / PI, 0), 1);
      const hue = (1 - ratio) * 220;
      const color = `hsl(${hue}, 70%, 55%)`;

      const posAngle = (i / N_QUBITS) * 2 * PI;
      const x = SCENE_RADIUS * Math.cos(posAngle);
      const y = SCENE_RADIUS * Math.sin(posAngle);
      const z = 0;

      scene.qubits.push({
        index: i,
        pos: new Vec3(x, y, z),
        angle: angle,
        color: color,
        radius: QUBIT_RADIUS,
      });
    }
  }

  function createGates() {
    scene.gates = [];
    for (let layer = 0; layer < 3; layer++) {
      for (let i = 0; i < N_QUBITS; i++) {
        const ctrl = i;
        const tgt = (i + 1) % N_QUBITS;
        const ctrlQubit = scene.qubits[ctrl];
        const tgtQubit = scene.qubits[tgt];

        if (!ctrlQubit || !tgtQubit) continue;

        const p1 = ctrlQubit.pos.clone();
        p1.z += 0.5 * layer;

        const p2 = tgtQubit.pos.clone();
        p2.z += 0.5 * layer;

        scene.gates.push({
          layer: layer,
          type: "CNOT",
          p1: p1,
          p2: p2,
          color: "#4db8ff",
        });
      }
    }
  }

  function transformScene() {
    // Rotate all qubits
    scene.qubits.forEach(q => {
      q.pos.rotateX(scene.rotation.x);
      q.pos.rotateY(scene.rotation.y);
      q.pos.rotateZ(scene.rotation.z);
    });

    // Rotate all gates (re-create from rotated qubit positions would be better,
    // but for now rotate the line endpoints)
    scene.gates.forEach(g => {
      g.p1.rotateX(scene.rotation.x);
      g.p1.rotateY(scene.rotation.y);
      g.p1.rotateZ(scene.rotation.z);
      g.p2.rotateX(scene.rotation.x);
      g.p2.rotateY(scene.rotation.y);
      g.p2.rotateZ(scene.rotation.z);
    });
  }

  function render() {
    const width = canvas.width / window.devicePixelRatio;
    const height = canvas.height / window.devicePixelRatio;

    // Clear canvas
    ctx.fillStyle = "#0a1422";
    ctx.fillRect(0, 0, width, height);

    // Center of canvas
    const centerX = width / 2;
    const centerY = height / 2;

    // Draw gates (lines) first (depth sorting)
    scene.gates.forEach(gate => {
      const proj1 = gate.p1.project();
      const proj2 = gate.p2.project();

      const x1 = centerX + proj1.x * 100 * scene.zoom;
      const y1 = centerY - proj1.y * 100 * scene.zoom;
      const x2 = centerX + proj2.x * 100 * scene.zoom;
      const y2 = centerY - proj2.y * 100 * scene.zoom;

      ctx.strokeStyle = gate.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    });

    // Draw qubits (spheres as circles) sorted by depth
    const qubitsSorted = scene.qubits.slice().sort((a, b) => {
      const projA = a.pos.project();
      const projB = b.pos.project();
      return projA.depth - projB.depth;
    });

    qubitsSorted.forEach(qubit => {
      const proj = qubit.pos.project();
      const x = centerX + proj.x * 100 * scene.zoom;
      const y = centerY - proj.y * 100 * scene.zoom;
      const radius = (QUBIT_RADIUS * 100 * scene.zoom) / (qubit.pos.z + 8);

      // Draw shadow
      ctx.fillStyle = "rgba(0, 0, 0, 0.3)";
      ctx.beginPath();
      ctx.arc(x + 2, y + 2, radius * 0.8, 0, 2 * PI);
      ctx.fill();

      // Draw sphere with gradient
      const gradient = ctx.createRadialGradient(x - radius * 0.3, y - radius * 0.3, 0, x, y, radius);
      gradient.addColorStop(0, qubit.color.replace("55%", "75%"));
      gradient.addColorStop(1, qubit.color.replace("55%", "30%"));
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, 2 * PI);
      ctx.fill();

      // Draw border
      ctx.strokeStyle = qubit.color;
      ctx.lineWidth = 2;
      ctx.stroke();
    });

    // Draw labels
    const labelContainer = document.getElementById("qubit3dLabels");
    if (labelContainer && labelContainer.children.length === 0) {
      qubitsSorted.forEach(qubit => {
        const angle = qubit.angle;
        const degrees = (angle * 180 / PI).toFixed(2);
        const label = document.createElement("div");
        label.className = "qubit-label";
        label.innerHTML = `
          <div class="qubit-num">q${qubit.index}</div>
          <div class="qubit-angle">${angle.toFixed(3)} rad</div>
          <div class="qubit-deg">${degrees}°</div>
        `;
        labelContainer.appendChild(label);
      });
    }
  }

  function animate() {
    if (!isInitialized) return;

    // Auto-rotate
    scene.rotation.y += 0.005;
    scene.rotation.x += 0.001;

    // Apply mouse input
    if (mouse.down) {
      scene.rotation.y += mouse.dx * 0.01;
      scene.rotation.x += mouse.dy * 0.01;
      mouse.dx *= 0.9;
      mouse.dy *= 0.9;
    }

    // Re-create scene (transform fresh each frame)
    createQubits(scene.qubits.map(q => q.angle));
    createGates();
    transformScene();
    render();

    animationId = requestAnimationFrame(animate);
  }

  function setupMouseHandlers() {
    canvas.addEventListener("mousedown", e => {
      mouse.down = true;
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    });

    document.addEventListener("mousemove", e => {
      if (mouse.down) {
        mouse.dx = e.clientX - mouse.x;
        mouse.dy = e.clientY - mouse.y;
        mouse.x = e.clientX;
        mouse.y = e.clientY;
      }
    });

    document.addEventListener("mouseup", () => {
      mouse.down = false;
    });

    canvas.addEventListener("wheel", e => {
      e.preventDefault();
      scene.zoom *= e.deltaY > 0 ? 0.85 : 1.18;
      scene.zoom = Math.max(0.05, Math.min(15, scene.zoom));
    });
  }

  function setupResizeHandler() {
    window.addEventListener("resize", () => {
      if (!canvas) return;
      const width = container.offsetWidth || 800;
      const height = container.offsetHeight || 400;
      canvas.width = width * window.devicePixelRatio;
      canvas.height = height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    });
  }

  // Public API
  window.render3DVisualization = function (angles) {
    if (!isInitialized && !initCanvas()) {
      return;
    }

    if (!Array.isArray(angles) || angles.length < N_QUBITS) {
      console.error("[canvas-3d-visualizer] Invalid angles array:", angles);
      return;
    }

    createQubits(angles);
    createGates();

    if (!animationId) {
      setupMouseHandlers();
      setupResizeHandler();
      animate();
    }
  };
})();
