/**
 * MOON per-panel 3D animated canvases
 * Each .panel hosts its own 3D canvas (z-index 0, behind content) with a
 * unique animated theme. Themes are chosen from the panel's CSS class.
 * Every panel gets an independent requestAnimationFrame loop.
 */
(function () {
  "use strict";

  /* ---- theme assignment: class-key -> renderer key ---- */
  var THM = {
    logo:      "burst",
    title:     "flow",
    metric:    "pulse",
    nav:       "lattice",
    leftA:     "honeycomb",
    leftB:     "orbit",
    leftC:     "flux",
    logs:      "spark",
    rightA:    "lattice",
    rightB:    "flow",
    rightC:    "matrix",
    rightD:    "radar",
    brainPanel: "vortex",
    matrix:    "matrix",
    bcell:     "spark",
    settings:  "pulse"
  };

  function themeForPanel(p) {
    var c = p.classList;
    for (var i = 0; i < c.length; i++) {
      var k = THM[c[i]];
      if (k) return k;
    }
    return "spark";
  }

  /* ---- helpers ---- */
  var DPR = Math.min(2, window.devicePixelRatio || 1);

  function fit(cv, p) {
    var w = p.clientWidth || 200;
    var h = p.clientHeight || 100;
    cv.style.width  = w + "px";
    cv.style.height = h + "px";
    cv.width  = Math.max(2, Math.floor(w * DPR));
    cv.height = Math.max(2, Math.floor(h * DPR));
    var ctx = cv.getContext("2d");
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    return { w: w, h: h, ctx: ctx };
  }

  /* ---- renderers (ctx, w, h, t, state) ---- */

  function rBurst(ctx, w, h, t, s) {
    if (!s.p) {
      s.cx = w/2; s.cy = h/2;
      s.p = [];
      var n = Math.min(34, Math.max(18, Math.floor((w+h)/22)));
      for (var i = 0; i < n; i++) {
        s.p.push({
          a: i * (Math.PI*2/n) + Math.random()*0.25,
          r: Math.random() * Math.min(w, h) * 0.32,
          sp: 0.28 + Math.random()*0.42,
          ph: Math.random()*6,
          sz: 1 + Math.random()*2.2
        });
      }
    }
    var p = s.p, cx = s.cx, cy = s.cy;
    for (var i = 0; i < p.length; i++) {
      p[i].a += p[i].sp * 0.012;
      p[i].r += Math.sin(t*0.4 + p[i].ph) * 0.25;
      p[i].r = Math.max(6, Math.min(Math.min(w, h)*0.42, p[i].r));
    }
    // connections
    ctx.lineWidth = 0.4;
    for (var i = 0; i < p.length; i++) {
      for (var j = i+1; j < p.length; j++) {
        var dx = Math.cos(p[i].a)*p[i].r - Math.cos(p[j].a)*p[j].r;
        var dy = Math.sin(p[i].a)*p[i].r - Math.sin(p[j].a)*p[j].r;
        var d = Math.sqrt(dx*dx + dy*dy);
        if (d < 48) {
          var a = 0.28 * (1 - d/48);
          ctx.strokeStyle = "rgba(255," + (80 + a*80|0) + "," + (40 + a*50|0) + "," + a + ")";
          ctx.beginPath();
          ctx.moveTo(cx + Math.cos(p[i].a)*p[i].r, cy + Math.sin(p[i].a)*p[i].r);
          ctx.lineTo(cx + Math.cos(p[j].a)*p[j].r, cy + Math.sin(p[j].a)*p[j].r);
          ctx.stroke();
        }
      }
    }
    // particles
    for (var i = 0; i < p.length; i++) {
      var x = cx + Math.cos(p[i].a) * p[i].r;
      var y = cy + Math.sin(p[i].a) * p[i].r;
      var b = 0.5 + 0.5 * Math.sin(t + p[i].ph);
      ctx.beginPath();
      ctx.arc(x, y, p[i].sz * (0.7 + b*0.5), 0, Math.PI*2);
      ctx.fillStyle = "rgba(255," + (80 + b*80|0) + "," + (40 + b*40|0) + "," + (0.4 + b*0.4) + ")";
      ctx.fill();
      if (b > 0.7) {
        ctx.shadowBlur = 8; ctx.shadowColor = "rgba(255,80,40,0.4)";
        ctx.fill(); ctx.shadowBlur = 0;
      }
    }
    // center glow
    var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, 30);
    g.addColorStop(0, "rgba(255,80,40," + (0.15 + 0.1*Math.sin(t)) + ")");
    g.addColorStop(1, "rgba(255,30,10,0)");
    ctx.fillStyle = g;
    ctx.fillRect(cx-30, cy-30, 60, 60);
  }

  function rFlow(ctx, w, h, t, s) {
    if (!s.cols) {
      s.cols = Math.max(8, Math.floor(w / 12));
      s.glyphs = "0123456789ABCDEF█▓▒░▶▷◀◁◆◇◈◉●○⊕⊗∂∇∫∑∏";
      s.colsArr = [];
      for (var c = 0; c < s.cols; c++) {
        s.colsArr.push({
          x: c * (w / s.cols) + Math.random() * 3,
          sp: 0.4 + Math.random() * 0.7,
          off: Math.random() * 100,
          b: 0.3 + Math.random() * 0.4
        });
      }
    }
    var cols = s.colsArr;
    ctx.font = "8px 'Share Tech Mono', monospace";
    for (var c = 0; c < cols.length; c++) {
      var col = cols[c];
      var y = ((t * col.sp * 15 + col.off) % (h + 20)) - 10;
      var x = col.x + Math.sin(t * 0.3 + c) * 2;
      var chr = s.glyphs[Math.floor((c * 7 + y * 0.3) % s.glyphs.length)];
      var b = col.b;
      ctx.fillStyle = "rgba(255,80,60,0.04)";
      ctx.fillText(chr, x, y - 8);
      ctx.fillStyle = "rgba(255," + (100 + b*80|0) + "," + (60 + b*40|0) + "," + (0.4 + b*0.3) + ")";
      ctx.fillText(chr, x, y);
    }
  }

  function rPulse(ctx, w, h, t, s) {
    var cx = w/2, cy = h/2;
    for (var r = 0; r < 3; r++) {
      var phase = (t + r * 0.8) % 3;
      var radius = 8 + phase * 12;
      var a = Math.max(0, 1 - phase/3);
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI*2);
      ctx.strokeStyle = "rgba(255," + (60 + a*80|0) + "," + (30 + a*40|0) + "," + a + ")";
      ctx.lineWidth = 1 + a * 2;
      if (a > 0.3) {
        ctx.shadowBlur = 8; ctx.shadowColor = "rgba(255,60,30," + (a*0.4) + ")";
        ctx.stroke(); ctx.shadowBlur = 0;
      } else ctx.stroke();
    }
    var pulse = 0.5 + 0.5 * Math.sin(t * 2);
    ctx.beginPath();
    ctx.arc(cx, cy, 2 + pulse*2, 0, Math.PI*2);
    ctx.fillStyle = "rgba(255,80,40," + (0.5 + pulse*0.4) + ")";
    ctx.shadowBlur = 10; ctx.shadowColor = "rgba(255,60,30,0.5)";
    ctx.fill(); ctx.shadowBlur = 0;
  }

  function rLattice(ctx, w, h, t, s) {
    if (!s.pts) {
      var cols = 5, rows = 4;
      s.pts = []; s.cols = cols; s.rows = rows;
      var sx = w / (cols + 1), sy = h / (rows + 1);
      for (var r = 0; r < rows; r++) {
        for (var c = 0; c < cols; c++) {
          s.pts.push({
            x: sx * (c + 1), y: sy * (r + 1),
            ph: Math.random() * 6,
            sz: 1.4 + Math.random() * 1.4
          });
        }
      }
    }
    var pts = s.pts;
    for (var i = 0; i < pts.length; i++) {
      pts[i].x += Math.sin(t * 0.3 + pts[i].ph) * 0.15;
      pts[i].y += Math.cos(t * 0.25 + pts[i].ph * 1.3) * 0.15;
    }
    ctx.lineWidth = 0.4;
    for (var i = 0; i < pts.length; i++) {
      for (var j = i + 1; j < pts.length; j++) {
        var dx = pts[i].x - pts[j].x;
        var dy = pts[i].y - pts[j].y;
        var d = Math.sqrt(dx*dx + dy*dy);
        if (d < w * 0.35) {
          var a = 0.08 + 0.06 * Math.sin(t + i + j);
          ctx.strokeStyle = "rgba(255," + (80 + a*60|0) + "," + (40 + a*40|0) + "," + a + ")";
          ctx.beginPath();
          ctx.moveTo(pts[i].x, pts[i].y);
          ctx.lineTo(pts[j].x, pts[j].y);
          ctx.stroke();
        }
      }
    }
    for (var i = 0; i < pts.length; i++) {
      var n = pts[i];
      var b = 0.4 + 0.6 * Math.sin(t * 1.5 + n.ph);
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.sz * (0.7 + b*0.5), 0, Math.PI*2);
      ctx.fillStyle = "rgba(255," + (80 + b*80|0) + "," + (50 + b*40|0) + "," + (0.3 + b*0.5) + ")";
      ctx.fill();
      if (b > 0.7) {
        ctx.shadowBlur = 8; ctx.shadowColor = "rgba(255,80,40,0.4)";
        ctx.fill(); ctx.shadowBlur = 0;
      }
    }
  }

  function rHoneycomb(ctx, w, h, t, s) {
    if (!s.hexes) {
      s.hexes = [];
      var r = Math.max(8, Math.min(14, w / 10));
      var hh = r * Math.sqrt(3);
      var cols = Math.ceil(w / (r * 3)) + 2;
      var rows = Math.ceil(h / (hh * 0.75)) + 2;
      for (var row = 0; row < rows; row++) {
        for (var col = 0; col < cols; col++) {
          var cx = col * r * 3 + (row % 2) * r * 1.5 + r;
          var cy = row * hh * 0.75 + hh / 2;
          if (cx < -r || cx > w + r || cy < -hh || cy > h + hh) continue;
          s.hexes.push({ cx: cx, cy: cy, r: r, ph: Math.random() * 6 });
        }
      }
      s.r = r;
    }
    var hexes = s.hexes;
    var sx = (t * 25) % (w + 40) - 20;
    var sy = h / 2;
    for (var i = 0; i < hexes.length; i++) {
      var hx = hexes[i];
      var d = Math.sqrt((hx.cx - sx) * (hx.cx - sx) + (hx.cy - sy) * (hx.cy - sy));
      var hl = Math.max(0, 1 - d / (hx.r * 8));
      var p = 0.4 + 0.6 * Math.sin(t * 0.7 + hx.ph);
      ctx.beginPath();
      for (var j = 0; j < 6; j++) {
        var a = Math.PI / 3 * j - Math.PI / 6;
        var px = hx.cx + hx.r * Math.cos(a);
        var py = hx.cy + hx.r * Math.sin(a);
        if (j === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.closePath();
      var a2 = 0.1 + p*0.15 + hl*0.2;
      ctx.strokeStyle = "rgba(255," + (60 + p*50 + hl*40|0) + "," + (30 + p*20 + hl*20|0) + "," + a2 + ")";
      ctx.lineWidth = 0.5 + hl * 1.2;
      ctx.stroke();
      ctx.fillStyle = "rgba(255,30,10," + (0.02 + p*0.04 + hl*0.06) + ")";
      ctx.fill();
      if (hl > 0.1) {
        ctx.beginPath();
        ctx.arc(hx.cx, hx.cy, 1 + hl * 2, 0, Math.PI*2);
        ctx.fillStyle = "rgba(255," + (100 + hl*80|0) + "," + (50 + hl*40|0) + "," + (0.2 + hl*0.4) + ")";
        ctx.fill();
      }
    }
  }

  function rOrbit(ctx, w, h, t, s) {
    if (!s.rings) {
      s.rings = [];
      var cx = w/2, cy = h/2;
      for (var ri = 0; ri < 3; ri++) {
        s.rings.push({
          rx: 20 + ri * 12, ry: 12 + ri * 8,
          tilt: ri * 0.6 + 0.2, sp: 0.3 + ri * 0.1,
          ph: Math.random() * 6, n: 6 + ri * 2,
          cx: cx, cy: cy
        });
      }
    }
    for (var ri = 0; ri < s.rings.length; ri++) {
      var ring = s.rings[ri];
      var rot = t * ring.sp + ring.tilt;
      ctx.beginPath();
      ctx.ellipse(ring.cx, ring.cy, ring.rx, ring.ry, rot, 0, Math.PI*2);
      var a = 0.15 + 0.1 * Math.sin(t + ring.ph);
      ctx.strokeStyle = "rgba(255," + (80 + a*60|0) + "," + (40 + a*40|0) + "," + a + ")";
      ctx.lineWidth = 0.6 + a;
      ctx.stroke();
      for (var p = 0; p < ring.n; p++) {
        var angle = rot + p * Math.PI * 2 / ring.n;
        var px = ring.cx + Math.cos(angle) * ring.rx;
        var py = ring.cy + Math.sin(angle) * ring.ry;
        var b = 0.5 + 0.5 * Math.sin(t * 2 + p + ring.ph);
        ctx.beginPath();
        ctx.arc(px, py, 1.2 + b * 1.5, 0, Math.PI*2);
        ctx.fillStyle = "rgba(255," + (100 + b*80|0) + "," + (50 + b*40|0) + "," + (0.4 + b*0.4) + ")";
        ctx.fill();
        if (b > 0.7) {
          ctx.shadowBlur = 6; ctx.shadowColor = "rgba(255,80,40,0.3)";
          ctx.fill(); ctx.shadowBlur = 0;
        }
      }
    }
    var g = ctx.createRadialGradient(w/2, h/2, 0, w/2, h/2, 20);
    g.addColorStop(0, "rgba(255,60,30,0.12)");
    g.addColorStop(1, "rgba(255,20,5,0)");
    ctx.fillStyle = g;
    ctx.fillRect(w/2 - 20, h/2 - 20, 40, 40);
  }

  function rFlux(ctx, w, h, t, s) {
    var waves = 4;
    for (var wi = 0; wi < waves; wi++) {
      var yB = h * (wi + 1) / (waves + 1);
      var amp = 6 + wi * 3;
      var fr = 0.02 + wi * 0.008;
      var ph = t * 1.2 + wi * 1.5;
      ctx.beginPath();
      for (var x = 0; x <= w; x += 3) {
        var y = yB + Math.sin(x * fr + ph) * amp + Math.sin(x * fr * 2.3 + ph * 0.7) * amp * 0.3;
        if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      var a = 0.12 + 0.08 * Math.sin(t + wi);
      ctx.strokeStyle = "rgba(255," + (80 + a*60|0) + "," + (40 + a*40|0) + "," + a + ")";
      ctx.lineWidth = 0.7 + a;
      ctx.stroke();
      ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath();
      var grd = ctx.createLinearGradient(0, yB, 0, h);
      grd.addColorStop(0, "rgba(255,40,15," + (a * 0.06) + ")");
      grd.addColorStop(1, "rgba(255,10,0,0)");
      ctx.fillStyle = grd;
      ctx.fill();
    }
  }

  function rSpark(ctx, w, h, t, s) {
    if (!s.pool) {
      s.pool = [];
      for (var i = 0; i < 24; i++) s.pool.push(sparkNew(w, h));
    }
    var pool = s.pool;
    /* each frame, age all sparks; recycle dead ones; draw a subset for this panel */
    var start = (s.frame || 0) % 8;
    s.frame = (s.frame || 0) + 1;
    for (var i = 0; i < pool.length; i++) {
      var sp = pool[i];
      sp.x += (Math.random() - 0.5) * 2.5;
      sp.y -= sp.speed;
      sp.life -= 0.007;
      if (sp.life <= 0 || sp.y < -5) pool[i] = sparkNew(w, h);
    }
    for (var k = 0; k < 8; k++) {
      var sp = pool[(start + k) % pool.length];
      var b = sp.life;
      if (b <= 0) continue;
      ctx.beginPath();
      ctx.moveTo(sp.x, sp.y);
      ctx.lineTo(sp.x - sp.vx * 3, sp.y + 4);
      ctx.strokeStyle = "rgba(255," + (80 + b*80|0) + "," + (40 + b*40|0) + "," + (b * 0.5) + ")";
      ctx.lineWidth = 0.5 + b;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, 1 + b * 1.5, 0, Math.PI*2);
      ctx.fillStyle = "rgba(255," + (100 + b*100|0) + "," + (50 + b*50|0) + "," + b + ")";
      ctx.fill();
      if (b > 0.5) {
        ctx.shadowBlur = 6; ctx.shadowColor = "rgba(255,80,40,0.3)";
        ctx.fill(); ctx.shadowBlur = 0;
      }
    }
    function sparkNew(w, h) {
      return {
        x: Math.random() * w,
        y: h + 5 + Math.random() * 10,
        vx: (Math.random() - 0.5) * 1.2,
        speed: 0.4 + Math.random() * 0.7,
        life: 0.5 + Math.random() * 0.5
      };
    }
  }

  function rMatrix(ctx, w, h, t, s) {
    if (!s.grid) {
      s.grid = [];
      var cols = Math.floor(w / 14);
      var rows = Math.floor(h / 14);
      for (var r = 0; r < rows; r++) {
        for (var c = 0; c < cols; c++) {
          s.grid.push({
            x: c * 14 + 7, y: r * 14 + 7,
            ph: Math.random() * 6,
            active: Math.random() > 0.7
          });
        }
      }
    }
    var grid = s.grid;
    for (var i = 0; i < grid.length; i++) {
      var cell = grid[i];
      var p = 0.3 + 0.7 * Math.sin(t * 1.2 + cell.ph);
      var active = p > 0.6;
      var b = active ? (0.4 + 0.6 * p) : 0.06;
      ctx.fillStyle = "rgba(255," + (60 + b*80|0) + "," + (30 + b*40|0) + "," + b + ")";
      ctx.fillRect(cell.x - 2, cell.y - 2, 5, 5);
      if (active) {
        ctx.shadowBlur = 6; ctx.shadowColor = "rgba(255,60,30,0.3)";
        ctx.fillRect(cell.x - 2, cell.y - 2, 5, 5);
        ctx.shadowBlur = 0;
      }
    }
    // flow lines
    ctx.lineWidth = 0.3;
    for (var c = 0; c < 5; c++) {
      var x = (t * 20 + c * w / 5) % (w + 20) - 10;
      var yB = h / 2 + Math.sin(t + c) * h * 0.3;
      ctx.beginPath();
      ctx.moveTo(x, 0); ctx.lineTo(x + 3, yB);
      ctx.strokeStyle = "rgba(255,60,30," + (0.04 + 0.03 * Math.sin(t + c)) + ")";
      ctx.stroke();
    }
    // scan bar
    var scanY = (t * 18) % h;
    ctx.fillStyle = "rgba(255,80,40,0.015)";
    ctx.fillRect(0, scanY, w, 1);
  }

  function rRadar(ctx, w, h, t, s) {
    var cx = w/2, cy = h/2;
    var maxR = Math.min(w, h) * 0.4;
    for (var r = 1; r <= 3; r++) {
      var rad = maxR * r / 3;
      ctx.beginPath();
      ctx.arc(cx, cy, rad, 0, Math.PI*2);
      ctx.strokeStyle = "rgba(255,60,30," + (0.06 + r * 0.02) + ")";
      ctx.lineWidth = 0.4;
      ctx.stroke();
    }
    ctx.strokeStyle = "rgba(255,40,20,0.04)";
    ctx.lineWidth = 0.3;
    ctx.beginPath();
    ctx.moveTo(cx, 0); ctx.lineTo(cx, h);
    ctx.moveTo(0, cy); ctx.lineTo(w, cy);
    ctx.stroke();
    var sa = t * 1.5;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, maxR, sa - 0.5, sa + 0.5);
    ctx.closePath();
    var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR);
    g.addColorStop(0, "rgba(255,80,40,0.1)");
    g.addColorStop(0.7, "rgba(255,60,30,0.04)");
    g.addColorStop(1, "rgba(255,30,10,0)");
    ctx.fillStyle = g;
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(sa) * maxR, cy + Math.sin(sa) * maxR);
    ctx.strokeStyle = "rgba(255,100,50,0.4)";
    ctx.lineWidth = 0.8;
    ctx.stroke();
    for (var i = 0; i < 7; i++) {
      var a = (i * 1.1 + t * 0.15) % (Math.PI * 2);
      var d = maxR * (0.18 + (i % 3) * 0.18);
      var bx = cx + Math.cos(a) * d;
      var by = cy + Math.sin(a) * d;
      if (Math.sin(t * 2 + i) > 0.3) {
        ctx.beginPath();
        ctx.arc(bx, by, 1.5, 0, Math.PI*2);
        ctx.fillStyle = "rgba(255,80,40,0.6)";
        ctx.shadowBlur = 6; ctx.shadowColor = "rgba(255,60,30,0.3)";
        ctx.fill(); ctx.shadowBlur = 0;
      }
    }
  }

  function rVortex(ctx, w, h, t, s) {
    var cx = w/2, cy = h/2;
    var maxR = Math.min(w, h) * 0.42;
    for (var a = 0; a < 3; a++) {
      var aa = a * Math.PI * 2 / 3;
      ctx.beginPath();
      for (var r = 5; r < maxR; r += 2) {
        var angle = aa + r * 0.14 + t * 0.35;
        var x = cx + Math.cos(angle) * r;
        var y = cy + Math.sin(angle) * r * 0.7;
        if (r === 5) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      var al = 0.1 + 0.08 * Math.sin(t + a);
      ctx.strokeStyle = "rgba(255," + (60 + al*60|0) + "," + (30 + al*40|0) + "," + al + ")";
      ctx.lineWidth = 0.6 + al;
      ctx.stroke();
    }
    var pu = 0.5 + 0.5 * Math.sin(t * 2);
    var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR * 0.3);
    g.addColorStop(0, "rgba(255,80,40," + (0.15 + pu * 0.15) + ")");
    g.addColorStop(0.5, "rgba(255,40,10," + (0.08 + pu * 0.06) + ")");
    g.addColorStop(1, "rgba(255,10,0,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(cx, cy, maxR * 0.3, 0, Math.PI*2);
    ctx.fill();
    for (var i = 0; i < 14; i++) {
      var or = maxR * 0.5 + Math.sin(t * 0.5 + i * 2) * 18;
      var ang = t * 0.5 + i * 0.8 + Math.sin(t * 0.3 + i) * 0.5;
      var x = cx + Math.cos(ang) * or;
      var y = cy + Math.sin(ang) * or * 0.7;
      var b = 0.3 + 0.7 * Math.sin(t + i);
      ctx.beginPath();
      ctx.arc(x, y, 1 + b, 0, Math.PI*2);
      ctx.fillStyle = "rgba(255," + (100 + b*80|0) + "," + (50 + b*40|0) + "," + (0.3 + b*0.4) + ")";
      ctx.fill();
      if (b > 0.6) {
        ctx.shadowBlur = 5; ctx.shadowColor = "rgba(255,80,40,0.3)";
        ctx.fill(); ctx.shadowBlur = 0;
      }
    }
  }

  /* ---- dispatch ---- */
  var RENDERERS = {
    burst: rBurst, flow: rFlow, pulse: rPulse, lattice: rLattice,
    honeycomb: rHoneycomb, orbit: rOrbit, flux: rFlux,
    spark: rSpark, matrix: rMatrix, radar: rRadar, vortex: rVortex
  };

  /* ---- one canvas + rAF loop per panel ---- */
  var panels = document.querySelectorAll(".panel");
  var g_loopers = [];

  for (var i = 0; i < panels.length; i++) {
    (function (panel) {
      var theme = themeForPanel(panel);
      var cv = document.createElement("canvas");
      cv.className = "panel3d";
      var r = fit(cv, panel);
      panel.prepend(cv);

      var st = {
        panel: panel, cv: cv, ctx: r.ctx,
        theme: theme,
        w: r.w, h: r.h, t: 0, s: {}
      };

      function frame() {
        st.t += 0.016;
        var rr = fit(st.cv, st.panel);
        st.w = rr.w; st.h = rr.h; st.ctx = rr.ctx;
        st.ctx.clearRect(0, 0, st.w, st.h);
        var fn = RENDERERS[st.theme];
        if (fn) fn(st.ctx, st.w, st.h, st.t, st.s);
        requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
      g_loopers.push(st);
    })(panels[i]);
  }

  /* ---- resize handler ---- */
  var rt;
  window.addEventListener("resize", function () {
    if (rt) clearTimeout(rt);
    rt = setTimeout(function () {
      for (var i = 0; i < g_loopers.length; i++) {
        var st = g_loopers[i];
        var pw = st.panel.clientWidth || 200;
        var ph = st.panel.clientHeight || 100;
        st.cv.style.width  = pw + "px";
        st.cv.style.height = ph + "px";
        st.cv.width  = Math.max(2, Math.floor(pw * DPR));
        st.cv.height = Math.max(2, Math.floor(ph * DPR));
        st.ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
        st.w = pw; st.h = ph;
      }
    }, 100);
  });

})();
