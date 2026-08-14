/* MOON Ultron — MediaPipe HandLandmarker gesture control (optional).
 * Loaded as an ES module. Drives window.__ultron.setGesture(...).
 * Gesture map: fist=idle, open=listening, victory=speaking, point=executing.
 * If no camera / permission denied, it logs and the avatar keeps working
 * via normal state/mood (graceful degrade). Fully local (vendored wasm+model). */
import { FilesetResolver, HandLandmarker } from "./mediapipe/vision_bundle.mjs";

const G = { FIST: "fist", OPEN: "open", VICTORY: "victory", POINT: "point", NONE: "none" };
let last = G.NONE, lastChange = 0;

function classify(lm) {
  // lm: 21 normalized landmarks. fingers extended if tip is farther from wrist than pip.
  const wrist = lm[0];
  const tips = [4, 8, 12, 16, 20], pips = [3, 6, 10, 14, 18];
  let extended = 0;
  for (let i = 0; i < 5; i++) {
    const t = lm[tips[i]], p = lm[pips[i]];
    const dt = Math.hypot(t.x - wrist.x, t.y - wrist.y);
    const dp = Math.hypot(p.x - wrist.x, p.y - wrist.y);
    if (dt > dp + 0.02) extended++;
  }
  const thumb = lm[4].x < lm[3].x - 0.02 || lm[4].x > lm[3].x + 0.02;
  if (extended === 0) return G.FIST;
  if (extended >= 4) return G.OPEN;
  // victory: index + middle extended, ring + pinky folded
  const idx = Math.hypot(lm[8].x - wrist.x, lm[8].y - wrist.y) > Math.hypot(lm[6].x - wrist.x, lm[6].y - wrist.y) + 0.02;
  const mid = Math.hypot(lm[12].x - wrist.x, lm[12].y - wrist.y) > Math.hypot(lm[10].x - wrist.x, lm[10].y - wrist.y) + 0.02;
  const ring = Math.hypot(lm[16].x - wrist.x, lm[16].y - wrist.y) > Math.hypot(lm[14].x - wrist.x, lm[14].y - wrist.y) + 0.02;
  const pink = Math.hypot(lm[20].x - wrist.x, lm[20].y - wrist.y) > Math.hypot(lm[18].x - wrist.x, lm[18].y - wrist.y) + 0.02;
  if (idx && mid && !ring && !pink) return G.VICTORY;
  if (idx && !mid && !ring && !pink) return G.POINT;
  return G.NONE;
}

async function main() {
  const video = document.createElement("video");
  video.autoplay = true; video.muted = true; video.playsInline = true;
  video.style.cssText = "position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;";
  document.body.appendChild(video);

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 } });
  } catch (e) {
    console.warn("[handtrack] camera unavailable — gesture control disabled (avatar still active):", e.message);
    return;
  }
  video.srcObject = stream;
  await video.play().catch(() => {});

  const fileset = await FilesetResolver.forVisionTasks("./mediapipe/wasm");
  const landmarker = await HandLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: "./mediapipe/hand_landmarker.task", delegate: "GPU" },
    numHands: 1, runningMode: "VIDEO"
  });

  window.__ultronStateHook = (s) => { /* bridge to app state if present */ if (window.__stateBridge) window.__stateBridge(s); };

  function frame() {
    if (video.readyState >= 2) {
      const res = landmarker.detectForVideo(video, performance.now());
      let g = G.NONE;
      if (res && res.landmarks && res.landmarks.length) g = classify(res.landmarks[0]);
      const now = performance.now();
      if (g !== last && now - lastChange > 400) {
        last = g; lastChange = now;
        if (window.__ultron) window.__ultron.setGesture(g);
      }
    }
    requestAnimationFrame(frame);
  }
  frame();
  console.log("[handtrack] MediaPipe HandLandmarker active");
}
main().catch((e) => console.warn("[handtrack] init failed:", e.message));
