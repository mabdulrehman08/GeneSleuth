/* Dark theme switch and animated background: stars drift, then pull together into a rotating DNA double helix.
   Purely cosmetic. It does not touch the app's code or data. */
(() => {
  const KEY = "genesleuth-theme";
  const root = document.documentElement;
  let theme = "dark";
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") theme = saved;
  } catch (error) { /* storage can be blocked; fall back to dark */ }
  root.setAttribute("data-theme", theme);

  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const SPEED = reduced ? 0.3 : 1;
  const BEADS = 84;          // dots per strand
  const RUNGS = 5;           // dots between the strands at each rung
  const STARS = 150;
  const FORM_S = 6, HOLD_S = 24, SCATTER_S = 4;
  const TILT = -0.32;

  let canvas, ctx, W = 0, H = 0, dpr = 1, running = false, last = 0, clock = 0;
  let phase = "form", phaseTime = 0;
  const dots = [];           // helix dots
  const stars = [];          // free stars

  const rand = (a, b) => a + Math.random() * (b - a);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function makeDots() {
    dots.length = 0;
    for (let strand = 0; strand < 2; strand += 1) {
      for (let i = 0; i < BEADS; i += 1) {
        dots.push({ kind: "bead", strand, i, delay: (i / BEADS) * 3 + strand * 0.4 });
      }
    }
    for (let i = 0; i < BEADS; i += 2) {
      for (let k = 1; k <= RUNGS; k += 1) dots.push({ kind: "rung", i, k, delay: (i / BEADS) * 3 + 0.8 });
    }
    for (const dot of dots) {
      dot.x = rand(0, W); dot.y = rand(0, H);
      dot.vx = rand(-12, 12); dot.vy = rand(-12, 12);
      dot.z = 0; dot.r = rand(1.1, 2.1);
    }
  }

  function makeStars() {
    stars.length = 0;
    for (let n = 0; n < STARS; n += 1) {
      stars.push({
        x: rand(0, W), y: rand(0, H), vx: rand(-6, 6), vy: rand(-6, 6),
        r: rand(0.5, 1.5), tw: rand(0, 6.28), ts: rand(0.6, 2),
      });
    }
  }

  function resize() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    const oldW = W || window.innerWidth, oldH = H || window.innerHeight;
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    for (const item of [...dots, ...stars]) { item.x *= W / oldW; item.y *= H / oldH; }
  }

  // Helix position of one strand bead, in screen space, plus depth z in [-1, 1].
  function beadPoint(strand, i, time) {
    const length = Math.hypot(W, H) * 1.08;
    const radius = Math.max(70, Math.min(W, H) * 0.12);
    const u = (i / (BEADS - 1) - 0.5) * length;
    const angle = i * 0.72 + time * 0.7 + strand * Math.PI;
    const px = Math.cos(angle) * radius;
    const cos = Math.cos(TILT), sin = Math.sin(TILT);
    return {
      x: W * 0.7 + px * cos - u * sin,
      y: H * 0.5 + px * sin + u * cos,
      z: Math.sin(angle),
    };
  }

  function targetFor(dot, time) {
    if (dot.kind === "bead") return beadPoint(dot.strand, dot.i, time);
    const a = beadPoint(0, dot.i, time), b = beadPoint(1, dot.i, time);
    const f = dot.k / (RUNGS + 1);
    return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, z: a.z + (b.z - a.z) * f };
  }

  function formedness() {
    if (phase === "form") return clamp(phaseTime / FORM_S, 0, 1);
    if (phase === "hold") return 1;
    return clamp(1 - phaseTime / (SCATTER_S * 0.6), 0, 1);
  }

  function step(dt) {
    clock += dt;
    phaseTime += dt;
    if (phase === "form" && phaseTime > FORM_S) { phase = "hold"; phaseTime = 0; }
    else if (phase === "hold" && phaseTime > HOLD_S) { phase = "scatter"; phaseTime = 0; }
    else if (phase === "scatter" && phaseTime > SCATTER_S) { phase = "form"; phaseTime = 0; }

    for (const star of stars) {
      star.x += star.vx * dt; star.y += star.vy * dt; star.tw += star.ts * dt;
      if (star.x < -5) star.x = W + 5; else if (star.x > W + 5) star.x = -5;
      if (star.y < -5) star.y = H + 5; else if (star.y > H + 5) star.y = -5;
    }

    for (const dot of dots) {
      // free drift always continues, so scattered dots look like stars
      dot.x += dot.vx * dt * 0.4; dot.y += dot.vy * dt * 0.4;
      const target = targetFor(dot, clock);
      let pull = 0;
      if (phase === "form") pull = clamp((phaseTime - dot.delay) / 1.5, 0, 1) * 0.1;
      else if (phase === "hold") pull = 0.2;
      else pull = 0;
      if (pull > 0) {
        const k = 1 - Math.pow(1 - pull, dt * 60);
        dot.x += (target.x - dot.x) * k; dot.y += (target.y - dot.y) * k;
        dot.z += (target.z - dot.z) * k;
      } else {
        dot.z *= 0.98;
        if (dot.x < -20) dot.x = W + 20; else if (dot.x > W + 20) dot.x = -20;
        if (dot.y < -20) dot.y = H + 20; else if (dot.y > H + 20) dot.y = -20;
      }
    }
  }

  function dot2(x, y, r, color, alpha) {
    ctx.globalAlpha = alpha * 0.28;
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(x, y, r * 3, 0, 6.2832); ctx.fill();
    ctx.globalAlpha = alpha;
    ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832); ctx.fill();
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.globalCompositeOperation = "lighter";

    for (const star of stars) {
      const twinkle = 0.45 + 0.4 * Math.sin(star.tw);
      dot2(star.x, star.y, star.r, "#cfd8ff", twinkle * 0.75);
    }

    const formed = formedness();
    // strand lines
    if (formed > 0.05) {
      ctx.lineWidth = 1;
      for (let strand = 0; strand < 2; strand += 1) {
        ctx.strokeStyle = strand ? "#ff6f7f" : "#9a90ff";
        ctx.globalAlpha = 0.22 * formed;
        ctx.beginPath();
        for (let i = 0; i < BEADS; i += 1) {
          const dot = dots[strand * BEADS + i];
          if (i === 0) ctx.moveTo(dot.x, dot.y); else ctx.lineTo(dot.x, dot.y);
        }
        ctx.stroke();
      }
    }

    // base-pair rungs
    if (formed > 0.05) {
      ctx.strokeStyle = "#9fe3ff";
      ctx.globalAlpha = 0.09 * formed;
      ctx.beginPath();
      for (let i = 0; i < BEADS; i += 2) {
        const a = dots[i], b = dots[BEADS + i];
        ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      }
      ctx.stroke();
    }

    // the "variant": one glowing amber bead travels along the helix once it has formed
    const variantIndex = Math.floor(((clock * 2.2) % BEADS));
    for (const dot of dots) {
      const depth = 0.65 + 0.35 * ((dot.z + 1) / 2);
      let color = dot.kind === "rung" ? "#9fe3ff" : (dot.strand ? "#ff8a98" : "#b1a8ff");
      let r = dot.r * depth * (dot.kind === "rung" ? 0.8 : 1.25);
      let alpha = (dot.kind === "rung" ? 0.7 : 0.95) * depth;
      if (formed > 0.9 && dot.kind === "bead" && dot.strand === 0 && Math.abs(dot.i - variantIndex) < 1) {
        color = "#ffc35a"; r *= 2.6; alpha = 1;
      }
      dot2(dot.x, dot.y, r, color, alpha);
    }

    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }

  function frame(now) {
    if (!running) return;
    const dt = Math.min(0.05, (now - last) / 1000) * SPEED;
    last = now;
    step(dt);
    draw();
    requestAnimationFrame(frame);
  }

  function start() {
    if (running || !canvas) return;
    running = true; last = performance.now();
    requestAnimationFrame(frame);
  }

  function stop() { running = false; }

  function apply(next) {
    theme = next;
    root.setAttribute("data-theme", theme);
    try { localStorage.setItem(KEY, theme); } catch (error) { /* ignore */ }
    const button = document.querySelector(".theme-toggle");
    if (button) {
      button.textContent = theme === "dark" ? "Light mode" : "Dark mode";
      button.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
    }
    if (theme === "dark") start(); else stop();
  }

  function setup() {
    canvas = document.createElement("canvas");
    canvas.id = "bg-canvas";
    canvas.setAttribute("aria-hidden", "true");
    document.body.prepend(canvas);
    ctx = canvas.getContext("2d");
    W = window.innerWidth; H = window.innerHeight;
    makeDots(); makeStars(); resize();

    const nav = document.querySelector(".masthead nav");
    if (nav) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "theme-toggle";
      button.addEventListener("click", () => apply(theme === "dark" ? "light" : "dark"));
      nav.append(button);
    }
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stop(); else if (theme === "dark") start();
    });
    apply(theme);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setup);
  else setup();
})();
