/* MOON Ultron Avatar — Three.js rendered robotic head (Iron-Man-film style).
 * Avatar-area only: sits inside #avatarStage, behind the HUD rings.
 * Driven by window.__ultron.setState(state) / setMood(mood).
 * No external assets; fully offline. CPU-friendly (capped DPR, low poly). */
(function () {
  "use strict";
  if (typeof THREE === "undefined") {
    console.warn("[ultron] THREE not loaded — skipping 3D avatar");
    return;
  }
  var canvas = document.getElementById("ultronCanvas");
  if (!canvas) { console.warn("[ultron] #ultronCanvas missing"); return; }

  var stage = document.getElementById("avatarStage") || canvas.parentElement;

  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 0.1, 6.2);

  // ---- Lighting: cinematic rim + key ----
  scene.add(new THREE.AmbientLight(0x223044, 0.9));
  var key = new THREE.DirectionalLight(0xbfdfff, 1.1); key.position.set(2, 3, 4); scene.add(key);
  var rimRed = new THREE.PointLight(0xff2638, 1.4, 30); rimRed.position.set(-3, -1, 2); scene.add(rimRed);
  var rimCyan = new THREE.PointLight(0x27d7e8, 1.0, 30); rimCyan.position.set(3, 1, -2); scene.add(rimCyan);

  // ---- Materials ----
  var metal = new THREE.MeshStandardMaterial({ color: 0x1b1f26, metalness: 0.95, roughness: 0.34 });
  var metalDark = new THREE.MeshStandardMaterial({ color: 0x0e1116, metalness: 0.9, roughness: 0.5 });
  var trim = new THREE.MeshStandardMaterial({ color: 0x2a2f38, metalness: 1.0, roughness: 0.25 });

  var head = new THREE.Group();
  scene.add(head);

  // Skull dome
  var dome = new THREE.Mesh(new THREE.SphereGeometry(1.18, 40, 32, 0, Math.PI * 2, 0, Math.PI * 0.62), metal);
  head.add(dome);
  // Lower skull / cheeks
  var jaw = new THREE.Mesh(new THREE.SphereGeometry(1.0, 40, 28), metal);
  jaw.scale.set(1.02, 0.92, 1.0); jaw.position.y = -0.55; head.add(jaw);
  // Face plate (front mask)
  var plate = new THREE.Mesh(new THREE.SphereGeometry(1.04, 40, 28, 0, Math.PI * 2, Math.PI * 0.18, Math.PI * 0.5), metalDark);
  plate.position.z = 0.12; head.add(plate);
  // Brow ridge
  var brow = new THREE.Mesh(new THREE.TorusGeometry(0.92, 0.06, 12, 40, Math.PI), trim);
  brow.rotation.set(Math.PI, 0, 0); brow.position.set(0, 0.42, 0.62); head.add(brow);
  // Chin seam
  var chin = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.5, 0.4, 24), metalDark);
  chin.position.set(0, -1.18, 0.2); head.add(chin);

  // ---- Eyes (iconic wide-set glow) ----
  function makeEye(x) {
    var g = new THREE.Group();
    var socket = new THREE.Mesh(new THREE.SphereGeometry(0.26, 24, 20), metalDark);
    g.add(socket);
    var glowMat = new THREE.MeshBasicMaterial({ color: 0x27d7e8, transparent: true, opacity: 0.95 });
    var core = new THREE.Mesh(new THREE.SphereGeometry(0.16, 24, 18), glowMat);
    g.add(core);
    // soft halo sprite
    var halo = new THREE.Sprite(new THREE.SpriteMaterial({
      map: makeGlowTexture(), color: 0x27d7e8, transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.85
    }));
    halo.scale.set(1.1, 1.1, 1.1); g.add(halo);
    g.position.set(x, 0.18, 0.92);
    g.userData = { core: core, glow: glowMat, halo: halo.material };
    head.add(g);
    return g;
  }
  function makeGlowTexture() {
    var c = document.createElement("canvas"); c.width = c.height = 128;
    var x = c.getContext("2d");
    var g = x.createRadialGradient(64, 64, 4, 64, 64, 64);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.25, "rgba(255,255,255,0.85)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    x.fillStyle = g; x.fillRect(0, 0, 128, 128);
    var t = new THREE.CanvasTexture(c); return t;
  }
  var eyeL = makeEye(-0.42), eyeR = makeEye(0.42);

  // ---- Mouth slit (pulses on speak) ----
  var mouthMat = new THREE.MeshBasicMaterial({ color: 0x27d7e8, transparent: true, opacity: 0.9 });
  var mouth = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.07, 0.08), mouthMat);
  mouth.position.set(0, -0.55, 0.95); head.add(mouth);

  // ---- Orbiting rings ----
  var rings = [];
  function makeRing(r, tube, tilt, color) {
    var m = new THREE.Mesh(new THREE.TorusGeometry(r, tube, 14, 80),
      new THREE.MeshStandardMaterial({ color: color, metalness: 1.0, roughness: 0.3,
        emissive: color, emissiveIntensity: 0.25 }));
    m.rotation.x = tilt; head.add(m); rings.push(m); return m;
  }
  makeRing(1.7, 0.025, 1.15, 0x8e0714);
  makeRing(1.95, 0.02, 0.6, 0x27d7e8);
  makeRing(2.2, 0.018, 1.9, 0x3a4250);

  // ---- State-driven appearance ----
  var COLORS = {
    idle: 0x27d7e8, listening: 0x27d7e8, speaking: 0xff2638,
    thinking: 0xffa030, executing: 0xff2638, success: 0x00ef9b, error: 0xff2638,
    warm: 0xff5a6a, focused: 0x27d7e8, curious: 0x9b6bff, calm: 0x27d7e8
  };
  var stateColor = COLORS.idle, moodColor = COLORS.focused, targetIntensity = 0.9;
  var speaking = false, t = 0;

  function setEyeColor(hex) {
    stateColor = hex;
    [eyeL, eyeR].forEach(function (e) {
      e.userData.glow.color.setHex(hex);
      e.userData.halo.color.setHex(hex);
    });
    mouthMat.color.setHex(hex);
  }
  function setState(s) {
    if (!s || s === "idle") { setEyeColor(moodColor); targetIntensity = 0.85; speaking = false; return; }
    if (COLORS[s] !== undefined) setEyeColor(COLORS[s]);
    speaking = (s === "speaking");
    targetIntensity = speaking ? 1.0 : 0.92;
  }
  function setMood(m) { if (COLORS[m] !== undefined) { moodColor = COLORS[m]; if (!speaking) setEyeColor(moodColor); } }

  // ---- Resize ----
  function resize() {
    var w = stage.clientWidth || 380, h = stage.clientHeight || 380;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize); resize();

  // ---- Animation ----
  function loop() {
    requestAnimationFrame(loop);
    t += 0.016;
    // gentle idle rotation + mouse parallax
    var px = (window.avatarHuman && window.avatarHuman.x) ? window.avatarHuman.x : 0;
    var py = (window.avatarHuman && window.avatarHuman.y) ? window.avatarHuman.y : 0;
    head.rotation.y += (px * 0.5 - head.rotation.y) * 0.06;
    head.rotation.x += (-py * 0.35 - head.rotation.x) * 0.06;
    head.position.y = Math.sin(t * 0.8) * 0.04;
    // rings spin
    rings[0].rotation.z += 0.004; rings[1].rotation.z -= 0.006; rings[2].rotation.y += 0.003;
    rings[1].rotation.x = 0.6; rings[2].rotation.x = 1.9;
    // eye pulse
    var pulse = speaking ? (0.7 + Math.abs(Math.sin(t * 9)) * 0.5) : (0.8 + Math.sin(t * 2) * 0.12);
    eyeL.userData.glow.opacity = pulse; eyeR.userData.glow.opacity = pulse;
    eyeL.userData.halo.opacity = pulse * 0.85; eyeR.userData.halo.opacity = pulse * 0.85;
    eyeL.userData.core.scale.setScalar(0.9 + Math.sin(t * 3) * 0.05);
    eyeR.userData.core.scale.setScalar(0.9 + Math.sin(t * 3 + 1) * 0.05);
    // mouth sync
    mouth.scale.y = speaking ? (0.4 + Math.abs(Math.sin(t * 14)) * 1.6) : 0.5;
    mouthMat.opacity = speaking ? 0.95 : 0.6;
    renderer.render(scene, camera);
  }
  loop();

  window.__ultron = { setState: setState, setMood: setMood, renderer: renderer };
  console.log("[ultron] 3D avatar active");
})();
