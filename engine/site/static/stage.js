/* 메인 3D 무대: 스포츠 공 4종(축구·배구·야구·농구).
   - 크롬 반사 조명, 공마다 떠다니는 리듬이 다르고 누르면 튀며 회전한다.
   - 시즌 종목(data-balls 첫 두 개)이 앞쪽 가운데에 크게 놓인다.
   - three.js 는 무대가 보일 때만 불러오고, 화면 밖이거나 탭이 숨겨지면 멈춘다.
   - WebGL 이 없으면 대체 이미지를 그대로 둔다. */
(function () {
  "use strict";
  var stage = document.querySelector("[data-stage]");
  if (!stage) return;
  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var THREE_URL = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js";

  function webglOK() {
    try { var c = document.createElement("canvas"); return !!(c.getContext("webgl") || c.getContext("experimental-webgl")); }
    catch (e) { return false; }
  }
  if (!webglOK()) return;

  function loadThree(cb) {
    if (window.THREE) return cb();
    var s = document.createElement("script");
    s.src = THREE_URL; s.async = true; s.crossOrigin = "anonymous"; s.onload = cb;
    document.head.appendChild(s);
  }
  var started = false;
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (e.isIntersecting && !started) { started = true; loadThree(init); }
      if (window.__stageVisible) window.__stageVisible(e.isIntersecting);
    });
  }, { threshold: 0.05 });
  io.observe(stage);

  /* ── 절차적 텍스처 (정거원통 투영 1024×512) ── */
  var W = 1024, H = 512;
  function hash(x, y) { var h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return h - Math.floor(h); }
  function dirAt(px, py) {
    var lat = (0.5 - (py + 0.5) / H) * Math.PI, lon = ((px + 0.5) / W) * 2 * Math.PI - Math.PI, cl = Math.cos(lat);
    return [-Math.cos(lon) * cl, Math.sin(lat), Math.sin(lon) * cl];
  }
  function toUV(v) { // 방향 → 픽셀 좌표 (dirAt 의 역변환)
    var len = Math.hypot(v[0], v[1], v[2]), x = v[0] / len, y = v[1] / len, z = v[2] / len;
    var lat = Math.asin(y), lon = Math.atan2(z, -x);
    return [((lon + Math.PI) / (2 * Math.PI)) * W, (0.5 - lat / Math.PI) * H];
  }
  function perPixel(fn) {
    var c = document.createElement("canvas"); c.width = W; c.height = H;
    var ctx = c.getContext("2d"), img = ctx.createImageData(W, H), d = img.data;
    for (var py = 0; py < H; py++) for (var px = 0; px < W; px++) {
      var o = fn(dirAt(px, py), px, py), i = (py * W + px) * 4;
      d[i] = o[0]; d[i + 1] = o[1]; d[i + 2] = o[2]; d[i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    return c;
  }
  // 야구공·테니스공의 8자형 솔기 곡선
  function seamPoints(n) {
    var pts = [], a = 0.42;
    for (var i = 0; i <= n; i++) {
      var t = i / n * Math.PI * 2;
      pts.push([Math.cos(t) - a * Math.cos(3 * t), Math.sin(t) + a * Math.sin(3 * t), 2 * Math.sqrt(a) * Math.sin(2 * t)]);
    }
    return pts;
  }
  function strokeOnSphere(ctx, pts, width, color, dash) {
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = "round";
    if (dash) ctx.setLineDash(dash); else ctx.setLineDash([]);
    ctx.beginPath();
    var prev = null;
    pts.forEach(function (p) {
      var uv = toUV(p);
      if (prev && Math.abs(uv[0] - prev[0]) > W / 2) { ctx.stroke(); ctx.beginPath(); ctx.moveTo(uv[0], uv[1]); }
      else if (!prev) ctx.moveTo(uv[0], uv[1]); else ctx.lineTo(uv[0], uv[1]);
      prev = uv;
    });
    ctx.stroke();
  }

  var PHI = (1 + Math.sqrt(5)) / 2;
  var ICO = [[-1, PHI, 0], [1, PHI, 0], [-1, -PHI, 0], [1, -PHI, 0], [0, -1, PHI], [0, 1, PHI], [0, -1, -PHI], [0, 1, -PHI], [PHI, 0, -1], [PHI, 0, 1], [-PHI, 0, -1], [-PHI, 0, 1]]
    .map(function (v) { var l = Math.hypot(v[0], v[1], v[2]); return [v[0] / l, v[1] / l, v[2] / l]; });
  var FACES = (function () { // 정이십면체 면 중심 20개 = 축구공 육각형 중심
    var out = [];
    for (var i = 0; i < 12; i++) for (var j = i + 1; j < 12; j++) for (var k = j + 1; k < 12; k++) {
      var a = ICO[i], b = ICO[j], c = ICO[k], dab = a[0] * b[0] + a[1] * b[1] + a[2] * b[2], dbc = b[0] * c[0] + b[1] * c[1] + b[2] * c[2], dac = a[0] * c[0] + a[1] * c[1] + a[2] * c[2];
      if (dab > 0.4 && dbc > 0.4 && dac > 0.4) { var m = [a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2]], l = Math.hypot(m[0], m[1], m[2]); out.push([m[0] / l, m[1] / l, m[2] / l]); }
    }
    return out;
  })();

  var MAKE = {
    soccer: function () {
      var centers = ICO.map(function (v) { return { v: v, pent: true }; }).concat(FACES.map(function (v) { return { v: v, pent: false }; }));
      return perPixel(function (n, px, py) {
        var best = -2, second = -2, pent = false;
        for (var i = 0; i < centers.length; i++) {
          var c = centers[i].v, d = n[0] * c[0] + n[1] * c[1] + n[2] * c[2];
          if (d > best) { second = best; best = d; pent = centers[i].pent; } else if (d > second) second = d;
        }
        var edge = best - second, g = hash(px, py) * 8;
        if (edge < 0.012) return [40, 40, 44];
        return pent ? [24 + g, 24 + g, 30 + g] : [244 - g, 244 - g, 240 - g];
      });
    },
    volleyball: function () {
      var cols = [[255, 61, 127], [24, 196, 176], [250, 250, 245]];
      return perPixel(function (n, px, py) {
        var ax = Math.abs(n[0]), ay = Math.abs(n[1]), az = Math.abs(n[2]), f, u, v;
        if (ax >= ay && ax >= az) { f = n[0] > 0 ? 0 : 1; u = n[1] / ax; v = n[2] / ax; }
        else if (ay >= az) { f = n[1] > 0 ? 2 : 3; u = n[2] / ay; v = n[0] / ay; }
        else { f = n[2] > 0 ? 4 : 5; u = n[0] / az; v = n[1] / az; }
        var s = (f >> 1) % 2 === 0 ? u : v, k = (s + 1) / 2 * 3, st = Math.min(2, Math.floor(k));
        var e = Math.min(Math.abs(k - Math.round(k)) / 1.5, (1 - Math.max(Math.abs(u), Math.abs(v))) * 0.9);
        var c = cols[(st + f) % 3], g = hash(px, py) * 6;
        if (e < 0.018) return [c[0] * .55, c[1] * .55, c[2] * .55];
        return [c[0] - g, c[1] - g, c[2] - g];
      });
    },
    basketball: function () {
      return perPixel(function (n, px, py) {
        var d = Math.min(Math.abs(n[1]), Math.abs(n[2]), Math.abs(Math.abs(n[2]) - 0.63) * 1.25), p = hash(px >> 1, py >> 1) > .55 ? 10 : -6;
        if (d < 0.011) return [26, 22, 20];
        return [214 + p, 98 + p * .6, 40];
      });
    },
    baseball: function () {
      // 솔기 = 구와 안장면 z = k(x² − y²) 의 교선(야구공·테니스공의 8자 곡선). 픽셀마다 곡선까지 거리를 근사한다.
      var K = 1.7;
      return perPixel(function (n, px, py) {
        var f = n[2] - K * (n[0] * n[0] - n[1] * n[1]);
        var gx = -2 * K * n[0], gy = 2 * K * n[1], gz = 1, gn = gx * n[0] + gy * n[1] + gz * n[2];
        var tx = gx - gn * n[0], ty = gy - gn * n[1], tz = gz - gn * n[2];       // 구면 접평면 위 기울기
        var dist = Math.abs(f) / Math.max(0.2, Math.hypot(tx, ty, tz));
        var g = hash(px, py) * 8, along = Math.atan2(n[1], n[0]) * 17 + n[2] * 12;
        if (dist < 0.012) return [200, 190, 176];                                     // 가죽 이음선
        if (dist > 0.02 && dist < 0.115 && (along - Math.floor(along)) < 0.55) return [196, 24, 36]; // 빨간 실밥
        return [247 - g, 244 - g, 236 - g];
      });
    }
  };
  var MAT = { // 재질: 거칠기·금속감·요철 세기
    soccer: { rough: .28, metal: .05, scale: [1, 1, 1], r: 1 },
    volleyball: { rough: .22, metal: .15, scale: [1, 1, 1], r: 1 },
    basketball: { rough: .6, metal: 0, scale: [1, 1, 1], r: 1.05 },
    baseball: { rough: .5, metal: 0, scale: [1, 1, 1], r: .78 }

  };

  function init() {
    var T = window.THREE;
    if (!T) return;
    var canvas = stage.querySelector("canvas"), renderer;
    try { renderer = new T.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true, powerPreference: "low-power" }); }
    catch (e) { return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
    renderer.outputEncoding = T.sRGBEncoding;
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFSoftShadowMap;

    var scene = new T.Scene();
    var cam = new T.PerspectiveCamera(32, 1, 0.1, 100);
    cam.position.set(0, 0.2, 11);

    // 무지갯빛 환경 반사(홀로그램 느낌)
    try {
      var pm = new T.PMREMGenerator(renderer), env = new T.Scene();
      var ec = document.createElement("canvas"); ec.width = 512; ec.height = 256;
      var ex = ec.getContext("2d"), gg = ex.createLinearGradient(0, 0, 512, 256);
      gg.addColorStop(0, "#ff3d7f"); gg.addColorStop(.35, "#ffd23d"); gg.addColorStop(.65, "#18c4b0"); gg.addColorStop(1, "#6c7bff");
      ex.fillStyle = gg; ex.fillRect(0, 0, 512, 256);
      env.add(new T.Mesh(new T.SphereGeometry(20, 32, 16), new T.MeshBasicMaterial({ map: new T.CanvasTexture(ec), side: T.BackSide })));
      scene.environment = pm.fromScene(env, 0.04).texture;
    } catch (e) { /* 환경맵 없이도 동작 */ }
    scene.add(new T.AmbientLight(0xffffff, 0.45));
    var key = new T.DirectionalLight(0xffffff, 1.25);
    key.position.set(3, 6, 7); key.castShadow = true; key.shadow.mapSize.set(1024, 1024); key.shadow.radius = 8;
    key.shadow.camera.left = -8; key.shadow.camera.right = 8; key.shadow.camera.top = 6; key.shadow.camera.bottom = -6;
    scene.add(key);
    var floorMat = new T.ShadowMaterial({ opacity: 0.12 });
    var floor = new T.Mesh(new T.PlaneGeometry(40, 40), floorMat);
    floor.rotation.x = -Math.PI / 2; floor.position.y = -2.1; floor.receiveShadow = true; scene.add(floor);
    function themeShadow() {
      var de = document.documentElement, dark = de.dataset.theme === "dark" || (!de.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
      floorMat.opacity = dark ? 0.35 : 0.12;
    }
    themeShadow(); document.addEventListener("themechange", themeShadow);

    var season = [];
    try { season = JSON.parse(stage.dataset.balls || "[]"); } catch (e) {}
    var order = season.filter(function (k) { return MAKE[k]; });
    ["volleyball", "basketball", "soccer", "baseball"].forEach(function (k) { if (order.indexOf(k) < 0) order.push(k); });
    // 배치: 앞쪽 큰 공 2개(시즌), 뒤쪽 2개
    var SLOTS = [[1.5, 0.1, 1.1, 1.25], [-1.6, -0.35, 0.5, 1.05], [3.9, 1.05, -1.6, .95], [-3.7, 1.15, -1.8, 1.05]];
    var balls = order.slice(0, 4).map(function (kind, i) {
      var m = MAT[kind], tex = new T.CanvasTexture(MAKE[kind]());
      tex.encoding = T.sRGBEncoding; tex.anisotropy = 4;
      var mesh = new T.Mesh(new T.SphereGeometry(1, 96, 64), new T.MeshStandardMaterial({ map: tex, roughness: m.rough, metalness: m.metal, envMapIntensity: 1.1 }));
      var s = SLOTS[i], size = m.r * s[3];
      mesh.scale.set(m.scale[0] * size, m.scale[1] * size, m.scale[2] * size);
      mesh.position.set(s[0], s[1], s[2]); mesh.castShadow = true;
      mesh.rotation.set(Math.random() * 2, Math.random() * 6, 0);
      scene.add(mesh);
      return { mesh: mesh, kind: kind, base: new T.Vector3(s[0], s[1], s[2]), phase: i * 1.7, spin: new T.Vector2(0.002 + i * 0.0006, 0.004 + i * 0.0008), y: 0, vy: 0, size: size };
    });

    function resize() {
      var w = stage.clientWidth, h = stage.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false); cam.aspect = w / h;
      cam.position.z = w / h < 1 ? 15 : w / h < 1.6 ? 12.5 : 11; // 좁은 화면에서는 뒤로 물러나 모두 보이게
      cam.updateProjectionMatrix();
    }
    resize(); window.addEventListener("resize", resize);

    var ray = new T.Raycaster(), ptr = new T.Vector2(), mx = 0, my = 0, drag = null;
    function pick(e) {
      var r = canvas.getBoundingClientRect();
      ptr.x = ((e.clientX - r.left) / r.width) * 2 - 1; ptr.y = -((e.clientY - r.top) / r.height) * 2 + 1;
      ray.setFromCamera(ptr, cam);
      var hit = ray.intersectObjects(balls.map(function (b) { return b.mesh; }))[0];
      return hit ? balls.filter(function (b) { return b.mesh === hit.object; })[0] : null;
    }
    canvas.addEventListener("pointermove", function (e) {
      var r = canvas.getBoundingClientRect();
      mx = (e.clientX - r.left) / r.width - 0.5; my = (e.clientY - r.top) / r.height - 0.5;
      if (drag) {
        var dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.moved += Math.abs(dx) + Math.abs(dy);
        drag.b.spin.set(dy * 0.004, dx * 0.004); drag.x = e.clientX; drag.y = e.clientY;
      } else canvas.style.cursor = pick(e) ? "pointer" : "";
      wake();
    });
    canvas.addEventListener("pointerdown", function (e) {
      var b = pick(e); if (!b) return;
      drag = { b: b, x: e.clientX, y: e.clientY, moved: 0 }; canvas.setPointerCapture(e.pointerId); wake();
    });
    function up() {
      if (drag && drag.moved < 6) { var b = drag.b; b.vy = 5 + Math.random(); b.spin.set((Math.random() - .5) * .25, (Math.random() - .5) * .35); }
      drag = null; wake();
    }
    canvas.addEventListener("pointerup", up); canvas.addEventListener("pointercancel", up);

    var visible = true, running = false, lastT = 0;
    window.__stageVisible = function (v) { visible = v; if (v) wake(); };
    document.addEventListener("visibilitychange", function () { if (!document.hidden) wake(); });
    function wake() { if (!running && visible && !document.hidden) { running = true; lastT = 0; requestAnimationFrame(tick); } }

    function tick(t) {
      if (!visible || document.hidden) { running = false; return; }
      var dt = lastT ? Math.min(0.033, (t - lastT) / 1000) : 0.016; lastT = t;
      var sec = t / 1000;
      balls.forEach(function (b) {
        if (b.y > 0 || b.vy > 0) { b.vy -= 14 * dt; b.y = Math.max(0, b.y + b.vy * dt); if (b.y === 0 && b.vy < 0) b.vy = Math.abs(b.vy) > 1.5 ? -b.vy * 0.45 : 0; }
        var bob = reduce ? 0 : Math.sin(sec * (0.8 + b.phase * 0.1) + b.phase) * 0.12;
        b.mesh.position.set(b.base.x + mx * 0.25 * (1 + b.base.z * 0.1), b.base.y + bob + b.y, b.base.z);
        if (!(drag && drag.b === b)) {
          b.mesh.rotation.x += b.spin.x; b.mesh.rotation.y += b.spin.y;
          b.spin.x += (0.002 - b.spin.x) * 0.02; b.spin.y += (0.004 * (b.phase % 2 ? -1 : 1) - b.spin.y) * 0.02;
        }
      });
      cam.position.x += (mx * 1.2 - cam.position.x) * 0.05;
      cam.position.y += (0.2 - my * 0.8 - cam.position.y) * 0.05;
      cam.lookAt(0, 0.1, 0);
      renderer.render(scene, cam);
      if (!stage.classList.contains("is-live")) stage.classList.add("is-live");
      if (reduce && !drag && balls.every(function (b) { return b.y === 0; })) { running = false; return; }
      requestAnimationFrame(tick);
    }
    wake();
  }
})();
