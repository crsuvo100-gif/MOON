/* MOON Ultron Avatar — advanced Three.js robotic head (Iron-Man-film style)
 * + MediaPipe HandLandmarker gesture control (optional, graceful degrade).
 * Avatar-area only. No external CDN; fully offline. CPU-friendly.
 * Gestures (from handtrack.js -> window.__ultron.setGesture):
 *   idle/fist, listening/open, speaking/victory, executing/point. */
(function () {
  "use strict";
  if (typeof THREE === "undefined") { console.warn("[ultron] THREE missing"); return; }
  var canvas = document.getElementById("ultronCanvas");
  if (!canvas) { console.warn("[ultron] #ultronCanvas missing"); return; }
  var stage = document.getElementById("avatarStage") || canvas.parentElement;

  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0.05, 6.2);

  scene.add(new THREE.AmbientLight(0x223044, 0.9));
  var key = new THREE.DirectionalLight(0xbfdfff, 1.1); key.position.set(2, 3, 4); scene.add(key);
  var rimRed = new THREE.PointLight(0xff2638, 1.5, 30); rimRed.position.set(-3, -1, 2); scene.add(rimRed);
  var rimCyan = new THREE.PointLight(0x27d7e8, 1.0, 30); rimCyan.position.set(3, 1, -2); scene.add(rimCyan);

  var metal = new THREE.MeshStandardMaterial({ color: 0x1b1f26, metalness: 0.96, roughness: 0.32 });
  var metalDark = new THREE.MeshStandardMaterial({ color: 0x0e1116, metalness: 0.9, roughness: 0.5 });
  var trim = new THREE.MeshStandardMaterial({ color: 0x2a2f38, metalness: 1.0, roughness: 0.22 });

  var head = new THREE.Group();
  scene.add(head);

  // Skull dome (angular-ish via low segment sphere)
  var dome = new THREE.Mesh(new THREE.SphereGeometry(1.18, 36, 28, 0, Math.PI * 2, 0, Math.PI * 0.6), metal);
  head.add(dome);
  var jaw = new THREE.Mesh(new THREE.SphereGeometry(1.0, 36, 24), metal);
  jaw.scale.set(1.02, 0.9, 1.0); jaw.position.y = -0.58; head.add(jaw);
  // Angular face plate (front mask) — faceted cylinder-ish
  var plate = new THREE.Mesh(new THREE.SphereGeometry(1.05, 36, 24, 0, Math.PI * 2, Math.PI * 0.18, Math.PI * 0.5), metalDark);
  plate.position.z = 0.12; head.add(plate);
  // Vertical "mouth" seam plate
  var seam = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.9, 0.1), trim);
  seam.position.set(0, -0.5, 1.0); head.add(seam);
  // Brow ridge
  var brow = new THREE.Mesh(new THREE.TorusGeometry(0.92, 0.06, 10, 40, Math.PI), trim);
  brow.rotation.set(Math.PI, 0, 0); brow.position.set(0, 0.42, 0.62); head.add(brow);
  // Side temples
  [-1, 1].forEach(function (s) {
    var t = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.5, 0.5), metalDark);
    t.position.set(s * 0.95, 0.05, 0.2); head.add(t);
  });
  // Chin
  var chin = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.5, 0.4, 20), metalDark);
  chin.position.set(0, -1.18, 0.2); head.add(chin);

  // ---- Glowing eyes (wide-set, iconic) ----
  function makeGlowTexture() {
    var c = document.createElement("canvas"); c.width = c.height = 128;
    var x = c.getContext("2d");
    var g = x.createRadialGradient(64, 64, 4, 64, 64, 64);
    g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.25, "rgba(255,255,255,0.85)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    x.fillStyle = g; x.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  }
  var glowTex = makeGlowTexture();
  function makeEye(x) {
    var g = new THREE.Group();
    var socket = new THREE.Mesh(new THREE.SphereGeometry(0.27, 22, 18), metalDark); g.add(socket);
    var glowMat = new THREE.MeshBasicMaterial({ color: 0x27d7e8, transparent: true, opacity: 0.95 });
    var core = new THREE.Mesh(new THREE.SphereGeometry(0.17, 22, 16), glowMat); g.add(core);
    var halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: 0x27d7e8, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.85 }));
    halo.scale.set(1.2, 1.2, 1.2); g.add(halo);
    // Eye beam (subtle forward light cone)
    var beam = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.6, 16, 1, true),
      new THREE.MeshBasicMaterial({ color: 0x27d7e8, transparent: true, opacity: 0.18, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false }));
    beam.rotation.x = Math.PI / 2; beam.position.z = 0.4; g.add(beam);
    g.position.set(x, 0.2, 0.94);
    g.userData = { core: core, glow: glowMat, halo: halo.material, beam: beam.material };
    head.add(g); return g;
  }
  var eyeL = makeEye(-0.44), eyeR = makeEye(0.44);

  // ---- Mouth slit (pulses on speak) ----
  var mouthMat = new THREE.MeshBasicMaterial({ color: 0x27d7e8, transparent: true, opacity: 0.9 });
  var mouth = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.07, 0.08), mouthMat);
  mouth.position.set(0, -0.5, 1.0); head.add(mouth);

  // ---- Orbiting rings ----
  var rings = [];
  function makeRing(r, tube, tilt, color) {
    var m = new THREE.Mesh(new THREE.TorusGeometry(r, tube, 12, 80),
      new THREE.MeshStandardMaterial({ color: color, metalness: 1.0, roughness: 0.3, emissive: color, emissiveIntensity: 0.25 }));
    m.rotation.x = tilt; head.add(m); rings.push(m); return m;
  }
  makeRing(1.7, 0.025, 1.15, 0x8e0714);
  makeRing(1.95, 0.02, 0.6, 0x27d7e8);
  makeRing(2.2, 0.018, 1.9, 0x3a4250);

  // ---- Particle field (advanced: floating data motes) ----
  var pcount = 260, pgeo = new THREE.BufferGeometry(), ppos = new Float32Array(pcount * 3);
  for (var i = 0; i < pcount; i++) {
    var rr = 2.4 + Math.random() * 1.6, a = Math.random() * Math.PI * 2, b = (Math.random() - 0.5) * Math.PI;
    ppos[i * 3] = Math.cos(a) * Math.cos(b) * rr; ppos[i * 3 + 1] = Math.sin(b) * rr * 0.8; ppos[i * 3 + 2] = Math.sin(a) * Math.cos(b) * rr;
  }
  pgeo.setAttribute("position", new THREE.BufferAttribute(ppos, 3));
  var particles = new THREE.Points(pgeo, new THREE.PointsMaterial({ color: 0x27d7e8, size: 0.03, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending, depthWrite: false }));
  scene.add(particles);

  // ---- State-driven appearance ----
  var COLORS = { idle: 0x27d7e8, listening: 0x27d7e8, speaking: 0xff2638, thinking: 0xffa030, executing: 0xff2638, success: 0x00ef9b, error: 0xff2638, warm: 0xff5a6a, focused: 0x27d7e8, curious: 0x9b6bff, calm: 0x27d7e8 };
  var stateColor = COLORS.idle, moodColor = COLORS.focused, speaking = false, t = 0, gestureSrc = false;

  function setEyeColor(hex) {
    stateColor = hex;
    [eyeL, eyeR].forEach(function (e) { e.userData.glow.color.setHex(hex); e.userData.halo.color.setHex(hex); e.userData.beam.color.setHex(hex); });
    mouthMat.color.setHex(hex);
  }
  function setState(s) {
    if (!s || s === "idle") { setEyeColor(gestureSrc ? stateColor : moodColor); speaking = false; return; }
    if (COLORS[s] !== undefined) setEyeColor(COLORS[s]);
    speaking = (s === "speaking");
  }
  function setMood(m) { if (COLORS[m] !== undefined) { moodColor = COLORS[m]; if (!speaking && !gestureSrc) setEyeColor(moodColor); } }
  function setGesture(g) {
    gestureSrc = true;
    var map = { fist: "idle", open: "listening", victory: "speaking", point: "executing", none: "idle" };
    var s = map[g] || "idle";
    if (window.__ultronStateHook) window.__ultronStateHook(s);
    setState(s);
  }

  function resize() {
    var w = stage.clientWidth || 380, h = stage.clientHeight || 380;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize); resize();

  function loop() {
    requestAnimationFrame(loop); t += 0.016;
    var px = (window.avatarHuman && window.avatarHuman.x) ? window.avatarHuman.x : 0;
    var py = (window.avatarHuman && window.avatarHuman.y) ? window.avatarHuman.y : 0;
    head.rotation.y += (px * 0.5 - head.rotation.y) * 0.06;
    head.rotation.x += (-py * 0.35 - head.rotation.x) * 0.06;
    head.position.y = Math.sin(t * 0.8) * 0.04;
    rings[0].rotation.z += 0.004; rings[1].rotation.z -= 0.006; rings[2].rotation.y += 0.003;
    rings[1].rotation.x = 0.6; rings[2].rotation.x = 1.9;
    particles.rotation.y += 0.0008;
    var pulse = speaking ? (0.7 + Math.abs(Math.sin(t * 9)) * 0.5) : (0.8 + Math.sin(t * 2) * 0.12);
    [eyeL, eyeR].forEach(function (e) {
      e.userData.glow.opacity = pulse; e.userData.halo.opacity = pulse * 0.85; e.userData.beam.opacity = speaking ? 0.32 : 0.16;
      e.userData.core.scale.setScalar(0.9 + Math.sin(t * 3) * 0.05);
    });
    mouth.scale.y = speaking ? (0.4 + Math.abs(Math.sin(t * 14)) * 1.6) : 0.5;
    mouthMat.opacity = speaking ? 0.95 : 0.6;
    renderer.render(scene, camera);
  }
  loop();

  window.__ultron = { setState: setState, setMood: setMood, setGesture: setGesture, renderer: renderer };
  console.log("[ultron] advanced 3D avatar active");
})();
