// PhishGuard — 3D Quantum Circuit Visualizer using Three.js

(function () {
  const canvas3dContainer = document.getElementById("canvas3dContainer");
  if (!canvas3dContainer) return;

  let scene, camera, renderer;
  let qubits = [];
  let gates = [];
  let animationId = null;
  let isInitialized = false;
  let initAttempts = 0;
  const MAX_INIT_ATTEMPTS = 5;

  const PI = Math.PI;
  const N_QUBITS = 4;
  const QUBIT_RADIUS = 0.5;
  const SCENE_RADIUS = 3;

  function checkWebGLSupport() {
    try {
      const canvas = document.createElement("canvas");
      return !!(window.WebGLRenderingContext && (canvas.getContext("webgl") || canvas.getContext("experimental-webgl")));
    } catch (e) {
      return false;
    }
  }

  function showError(message) {
    canvas3dContainer.innerHTML = `<div style="padding:30px;color:#ff6b6b;text-align:center;font-family:monospace;">⚠️ ${message}</div>`;
    console.error("[3d-visualizer]", message);
  }

  function initThreeScene() {
    initAttempts++;

    // Check if Three.js is loaded
    if (typeof THREE === "undefined") {
      if (initAttempts < MAX_INIT_ATTEMPTS) {
        console.warn(`[3d-visualizer] Three.js not loaded yet (attempt ${initAttempts}/${MAX_INIT_ATTEMPTS}), retrying...`);
        setTimeout(initThreeScene, 500);
        return;
      }
      showError("Three.js library failed to load. Please refresh the page or check your internet connection.");
      return;
    }

    // Check if WebGL is supported
    if (!checkWebGLSupport()) {
      showError("WebGL is not supported by your browser");
      return;
    }

    // Ensure container has computed dimensions
    const width = canvas3dContainer.offsetWidth || parseInt(window.getComputedStyle(canvas3dContainer).width) || 800;
    const height = canvas3dContainer.offsetHeight || parseInt(window.getComputedStyle(canvas3dContainer).height) || 400;

    if (width === 0 || height === 0) {
      if (initAttempts < MAX_INIT_ATTEMPTS) {
        console.warn("[3d-visualizer] Container dimensions not ready, retrying...");
        requestAnimationFrame(initThreeScene);
        return;
      }
      showError("Container dimensions could not be determined");
      return;
    }

    try {
      scene = new THREE.Scene();
      scene.background = new THREE.Color(0x0a1422);
      scene.fog = new THREE.Fog(0x0a1422, 20, 30);

      camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
      camera.position.set(0, 0, 8);
      camera.lookAt(0, 0, 0);

      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
      renderer.setSize(width, height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.shadowMap.enabled = true;
      renderer.domElement.style.display = "block";
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";

      // Clear container and add renderer
      canvas3dContainer.innerHTML = "";
      canvas3dContainer.appendChild(renderer.domElement);

      addLighting();
      addOrbitControls();
      setupResizeHandler();
      isInitialized = true;
      console.log("[3d-visualizer] Scene initialized successfully");
    } catch (err) {
      console.error("[3d-visualizer] Failed to initialize Three.js scene:", err);
      showError("Error initializing 3D scene: " + err.message);
    }
  }

  function addLighting() {
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(5, 10, 7);
    directionalLight.castShadow = true;
    directionalLight.shadow.mapSize.width = 2048;
    directionalLight.shadow.mapSize.height = 2048;
    scene.add(directionalLight);

    const pointLight = new THREE.PointLight(0x00d9ff, 0.4);
    pointLight.position.set(-5, -5, 5);
    scene.add(pointLight);
  }

  function addOrbitControls() {
    // Wait for OrbitControls to be available
    if (typeof THREE.OrbitControls === "undefined") {
      if (initAttempts < MAX_INIT_ATTEMPTS) {
        console.warn("[3d-visualizer] OrbitControls not available, waiting...");
        setTimeout(() => {
          addOrbitControls();
        }, 100);
        return;
      }
      console.warn("[3d-visualizer] OrbitControls not loaded, using static view");
      animate({ update: function() {} });
      return;
    }

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 2;
    controls.enablePan = true;
    controls.enableZoom = true;
    controls.minDistance = 3;
    controls.maxDistance = 20;

    animate(controls);
  }

  function animate(controls) {
    function animationLoop() {
      try {
        if (controls && controls.update) {
          controls.update();
        }
        if (renderer && scene && camera) {
          renderer.render(scene, camera);
        }
      } catch (err) {
        console.error("[3d-visualizer] Animation loop error:", err);
      }
      animationId = requestAnimationFrame(animationLoop);
    }
    animationLoop();
  }

  function setupResizeHandler() {
    window.addEventListener("resize", () => {
      if (!renderer || !camera || !scene) return;
      const width = canvas3dContainer.offsetWidth || 800;
      const height = canvas3dContainer.offsetHeight || 400;
      if (width > 0 && height > 0) {
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
      }
    });
  }

  function createQubits(angles) {
    if (!scene) return;

    qubits.forEach(qubit => {
      if (qubit.mesh) scene.remove(qubit.mesh);
    });
    qubits = [];

    for (let i = 0; i < N_QUBITS; i++) {
      const angle = angles[i] || 0;
      const ratio = Math.min(Math.max(angle / PI, 0), 1);
      const hue = (1 - ratio) * 220;
      const color = new THREE.Color().setHSL(hue / 360, 0.7, 0.55);

      const geometry = new THREE.IcosahedronGeometry(QUBIT_RADIUS, 4);
      const material = new THREE.MeshPhongMaterial({
        color: color,
        emissive: color.clone().multiplyScalar(0.5),
        shininess: 100,
        castShadow: true,
        receiveShadow: true,
      });
      const mesh = new THREE.Mesh(geometry, material);

      const posAngle = (i / N_QUBITS) * 2 * PI;
      mesh.position.x = SCENE_RADIUS * Math.cos(posAngle);
      mesh.position.y = SCENE_RADIUS * Math.sin(posAngle);
      mesh.position.z = 0;

      mesh.userData = { qubitIndex: i, angle: angle };
      mesh.castShadow = true;
      mesh.receiveShadow = true;

      scene.add(mesh);
      qubits.push({ index: i, mesh: mesh, angle: angle, color: color });
    }
  }

  function createGates() {
    if (!scene) return;

    gates.forEach(g => {
      if (g.mesh) scene.remove(g.mesh);
    });
    gates = [];

    for (let layer = 0; layer < 3; layer++) {
      for (let i = 0; i < N_QUBITS; i++) {
        const ctrl = i;
        const tgt = (i + 1) % N_QUBITS;

        const ctrlQubit = qubits[ctrl];
        const tgtQubit = qubits[tgt];

        if (!ctrlQubit || !tgtQubit) continue;

        const points = [
          new THREE.Vector3(ctrlQubit.mesh.position.x, ctrlQubit.mesh.position.y, ctrlQubit.mesh.position.z + 0.5 * layer),
          new THREE.Vector3(tgtQubit.mesh.position.x, tgtQubit.mesh.position.y, tgtQubit.mesh.position.z + 0.5 * layer),
        ];

        const lineGeometry = new THREE.BufferGeometry().setFromPoints(points);
        const lineMaterial = new THREE.LineBasicMaterial({ color: 0x4db8ff, linewidth: 2 });
        const line = new THREE.Line(lineGeometry, lineMaterial);
        scene.add(line);

        gates.push({ layer: layer, type: "CNOT", mesh: line });
      }
    }
  }

  function addLabels(angles) {
    const labelContainer = document.getElementById("qubit3dLabels");
    if (!labelContainer) return;

    labelContainer.innerHTML = "";
    for (let i = 0; i < N_QUBITS; i++) {
      const angle = angles[i] || 0;
      const degrees = (angle * 180 / PI).toFixed(2);
      const label = document.createElement("div");
      label.className = "qubit-label";
      label.innerHTML = `
        <div class="qubit-num">q${i}</div>
        <div class="qubit-angle">${angle.toFixed(3)} rad</div>
        <div class="qubit-deg">${degrees}°</div>
      `;
      labelContainer.appendChild(label);
    }
  }

  function render3DVisualization(angles) {
    // Validate input
    if (!Array.isArray(angles) || angles.length < N_QUBITS) {
      console.error("[3d-visualizer] Invalid angles array:", angles);
      return;
    }

    if (!isInitialized) {
      initThreeScene();
      // If still not initialized after init attempt, retry
      if (!isInitialized) {
        requestAnimationFrame(() => render3DVisualization(angles));
        return;
      }
    }

    // Add geometry to scene (safe to call multiple times)
    createQubits(angles);
    createGates();
    addLabels(angles);
  }

  // Expose functions globally
  window.render3DVisualization = render3DVisualization;
})();
