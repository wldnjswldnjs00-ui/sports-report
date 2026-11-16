/* 메인 3D 무대: 시즌 종목 공 두 개. 끌어서 회전, 눌러서 튕기기.
   - three.js 는 무대가 화면에 보일 때만 불러온다(첫 화면 속도 보호).
   - 화면 밖이거나 탭이 숨겨지면 렌더링을 멈춘다(CPU·배터리 보호).
   - WebGL 이 없거나 실패하면 SVG 대체 이미지를 그대로 둔다. */
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
    s.src = THREE_URL; s.async = true; s.crossOrigin = "anonymous";
    s.onload = cb;
    s.onerror = function () { /* 대체 이미지 유지 */ };
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

  /* ── 절차적 텍스처 ── */
  function hash(x, y) { var h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return h - Math.floor(h); }

  function equirect(w, h, shade) {
    var c = document.createElement("canvas"); c.width = w; c.height = h;
    var bump = document.createElement("canvas"); bump.width = w; bump.height = h;
    var ctx = c.getContext("2d"), bctx = bump.getContext("2d");
    var img = ctx.createImageData(w, h), bimg = bctx.createImageData(w, h);
    for (var y = 0; y < h; y++) {
      var lat = (0.5 - (y + 0.5) / h) * Math.PI, cl = Math.cos(lat), sl = Math.sin(lat);
      for (var x = 0; x < w; x++) {
        var lon = ((x + 0.5) / w) * 2 * Math.PI - Math.PI;
        // three.js SphereGeometry UV 와 같은 방향
        var nx = -Math.cos(lon) * cl, ny = sl, nz = Math.sin(lon) * cl;
        var out = shade(nx, ny, nz, x, y);
        var i = (y * w + x) * 4;
        img.data[i] = out[0]; img.data[i + 1] = out[1]; img.data[i + 2] = out[2]; img.data[i + 3] = 255;
        bimg.data[i] = bimg.data[i + 1] = bimg.data[i + 2] = out[3]; bimg.data[i + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0); bctx.putImageData(bimg, 0, 0);
    return { map: c, bump: bump };
  }

  function basketball() {
    var W = 0.012, C0 = 0.63;
    return equirect(1024, 512, function (nx, ny, nz, x, y) {
      // 적도 + 극을 지나는 큰 원(z=0 평면) + 큰 원 평면에 수직인 ±z 축 둘레의 곡선 두 개
      var d = Math.min(Math.abs(ny), Math.abs(nz), Math.abs(Math.abs(nz) - C0) * 1.25);
      var n = hash(x, y), n2 = hash(x * 0.5 | 0, y * 0.5 | 0);
      var pebble = n2 > 0.55 ? 1 : 0;
      var r = 206 + (pebble ? 10 : -6) + (n - 0.5) * 14, g = 92 + (pebble ? 6 : -4) + (n - 0.5) * 8, b = 40 + (n - 0.5) * 6;
      var bh = pebble ? 200 : 150;
      if (d < W) { var k = d / W; r = g = b = 22 + 20 * k; bh = 40 + 40 * k; }
      else if (d < W * 1.8) { var t = (d - W) / (W * 0.8); r *= 0.75 + 0.25 * t; g *= 0.75 + 0.25 * t; b *= 0.8 + 0.2 * t; bh = 90 + 60 * t; }
      return [r, g, b, bh];
    });
  }

  function volleyball() {
    var COLS = [[244, 196, 48], [32, 82, 168], [246, 244, 236]];
    var W = 0.018;
    return equirect(1024, 512, function (nx, ny, nz, x, y) {
      var ax = Math.abs(nx), ay = Math.abs(ny), az = Math.abs(nz), face, u, v;
      if (ax >= ay && ax >= az) { face = nx > 0 ? 0 : 1; u = ny / ax; v = nz / ax; }
      else if (ay >= az) { face = ny > 0 ? 2 : 3; u = nz / ay; v = nx / ay; }
      else { face = nz > 0 ? 4 : 5; u = nx / az; v = ny / az; }
      // 이웃 면끼리 줄무늬 방향을 엇갈리게
      var s = (face >> 1) % 2 === 0 ? u : v;
      var strip = Math.min(2, Math.floor((s + 1) / 2 * 3));
      var edgeStrip = Math.abs(((s + 1) / 2 * 3) - Math.round((s + 1) / 2 * 3)) / 3;
      var edgeFace = 1 - Math.max(Math.abs(u), Math.abs(v));
      var col = COLS[(strip + face) % 3];
      var n = hash(x, y) - 0.5;
      var r = col[0] + n * 6, g = col[1] + n * 6, b = col[2] + n * 6, bh = 170 + n * 10;
      var e = Math.min(edgeStrip * 1.5, edgeFace * 0.9);
      if (e < W) { var k = e / W; r *= 0.55 + 0.45 * k; g *= 0.55 + 0.45 * k; b *= 0.55 + 0.45 * k; bh = 60 + 110 * k; }
      return [r, g, b, bh];
    });
  }

  var MAKERS = { basketball: basketball, volleyball: volleyball };

  function init() {
    var T = window.THREE;
    if (!T) return;
    var canvas = stage.querySelector("canvas");
    var renderer;
    try { renderer = new T.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true, powerPreference: "low-power" }); }
    catch (e) { return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = T.PCFSoftShadowMap;
    renderer.outputEncoding = T.sRGBEncoding;
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;

    var scene = new T.Scene();
    var cam = new T.PerspectiveCamera(30, 1, 0.1, 100);
    cam.position.set(0, 1.6, 9.2);
    cam.lookAt(0, 0.6, 0);

    scene.add(new T.HemisphereLight(0xfff4e6, 0x3a2f25, 0.75));
    var key = new T.DirectionalLight(0xffffff, 1.35);
    key.position.set(-2.5, 9, 3.5);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.left = -5; key.shadow.camera.right = 5; key.shadow.camera.top = 5; key.shadow.camera.bottom = -5;
    key.shadow.radius = 6;
    scene.add(key);
    var rim = new T.DirectionalLight(0xffd2b0, 0.55);
    rim.position.set(5, 2, -4);
    scene.add(rim);

    var floorMat = new T.ShadowMaterial({ opacity: 0.18 });
    var floor = new T.Mesh(new T.PlaneGeometry(30, 30), floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    function themeShadow() {
      var dark = document.documentElement.dataset.theme === "dark" ||
        (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
      floorMat.opacity = dark ? 0.45 : 0.18;
    }
    themeShadow();
    document.addEventListener("themechange", themeShadow);

    var kinds = [];
    try { kinds = JSON.parse(stage.dataset.balls || "[]"); } catch (e) {}
    kinds = kinds.filter(function (k) { return MAKERS[k]; });
    if (!kinds.length) kinds = ["basketball", "volleyball"];

    var R = 1.05;
    var geo = new T.SphereGeometry(R, 96, 64);
    var balls = kinds.slice(0, 2).map(function (kind, i) {
      var tex = MAKERS[kind]();
      var map = new T.CanvasTexture(tex.map); map.encoding = T.sRGBEncoding; map.anisotropy = 4;
      var bump = new T.CanvasTexture(tex.bump);
      var mat = new T.MeshStandardMaterial({
        map: map, bumpMap: bump, bumpScale: kind === "basketball" ? 0.018 : 0.01,
        roughness: kind === "basketball" ? 0.72 : 0.5, metalness: 0
      });
      var mesh = new T.Mesh(geo, mat);
      mesh.castShadow = true;
      var x = i === 0 ? -1.25 : 1.3, z = i === 0 ? 0.2 : -0.6;
      mesh.position.set(x, R, z);
      mesh.rotation.set(0.35 + i, i * 1.7, 0.2);
      scene.add(mesh);
      return {
        mesh: mesh, kind: kind, baseX: x, z: z,
        y: R + 0.6 + i * 0.4, vy: 0, // 첫 등장: 위에서 떨어져 튄다
        spin: new T.Vector2(0.0025 * (i ? -1 : 1), 0.004), squash: 0, phase: i * 2.1
      };
    });
    balls.forEach(function (b, i) { b.y = R + 2.4 + i * 0.9; });

    function resize() {
      var w = stage.clientWidth, h = stage.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      cam.aspect = w / h;
      cam.fov = w / h < 1.1 ? 38 : 30;
      cam.updateProjectionMatrix();
    }
    resize();
    window.addEventListener("resize", resize);

    /* 상호작용 */
    var ray = new T.Raycaster(), ptr = new T.Vector2();
    var drag = null, last = { x: 0, y: 0, t: 0 };
    function pick(e) {
      var r = canvas.getBoundingClientRect();
      ptr.x = ((e.clientX - r.left) / r.width) * 2 - 1;
      ptr.y = -((e.clientY - r.top) / r.height) * 2 + 1;
      ray.setFromCamera(ptr, cam);
      var hit = ray.intersectObjects(balls.map(function (b) { return b.mesh; }))[0];
      return hit ? balls.filter(function (b) { return b.mesh === hit.object; })[0] : null;
    }
    canvas.addEventListener("pointerdown", function (e) {
      var b = pick(e);
      if (!b) return;
      drag = { ball: b, x0: e.clientX, y0: e.clientY, moved: 0 };
      last = { x: e.clientX, y: e.clientY, t: performance.now() };
      canvas.setPointerCapture(e.pointerId);
      wake();
    });
    canvas.addEventListener("pointermove", function (e) {
      if (!drag) { canvas.style.cursor = pick(e) ? "pointer" : ""; return; }
      var dx = e.clientX - last.x, dy = e.clientY - last.y;
      drag.moved += Math.abs(dx) + Math.abs(dy);
      drag.ball.mesh.rotation.y += dx * 0.012;
      drag.ball.mesh.rotation.x += dy * 0.012;
      var dt = Math.max(16, performance.now() - last.t);
      drag.ball.spin.set(dy * 0.012 * 16 / dt, dx * 0.012 * 16 / dt);
      last = { x: e.clientX, y: e.clientY, t: performance.now() };
      wake();
    });
    function up() {
      if (!drag) return;
      if (drag.moved < 6) { // 클릭: 튕기기
        var b = drag.ball;
        b.vy = 7.2 + Math.random() * 1.2;
        b.spin.set((Math.random() - 0.5) * 0.08, (Math.random() - 0.5) * 0.12);
      }
      drag = null;
      wake();
    }
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);

    /* 루프 */
    var visible = true, running = false, lastT = 0, idleSince = performance.now();
    window.__stageVisible = function (v) { visible = v; if (v) wake(); };
    document.addEventListener("visibilitychange", function () { if (!document.hidden) wake(); });
    function wake() { idleSince = performance.now(); if (!running && visible && !document.hidden) { running = true; lastT = 0; requestAnimationFrame(tick); } }

    var G = -16, REST = 0.58;
    function tick(t) {
      if (!visible || document.hidden) { running = false; return; }
      var dt = lastT ? Math.min(0.033, (t - lastT) / 1000) : 0.016;
      lastT = t;
      var anyMoving = false;
      balls.forEach(function (b) {
        // 중력과 바닥 반발
        if (b.y > R + 0.0005 || b.vy > 0) {
          b.vy += G * dt;
          b.y += b.vy * dt;
          if (b.y < R) {
            b.y = R;
            if (Math.abs(b.vy) > 1.2) { b.squash = Math.min(0.22, Math.abs(b.vy) * 0.022); b.vy = -b.vy * REST; }
            else b.vy = 0;
          }
          anyMoving = true;
        }
        b.squash *= 0.82;
        var float = reduce ? 0 : Math.sin(t / 1000 * 1.3 + b.phase) * 0.04;
        var sq = b.squash;
        b.mesh.scale.set(1 + sq * 0.6, 1 - sq, 1 + sq * 0.6);
        b.mesh.position.set(b.baseX, b.y - sq * R + (b.vy === 0 ? float + 0.04 : 0), b.z);
        if (drag && drag.ball === b) return;
        b.mesh.rotation.x += b.spin.x;
        b.mesh.rotation.y += b.spin.y;
        b.spin.multiplyScalar(0.975);
        var idleX = 0.0012, idleY = 0.0035 * (b.kind === "volleyball" ? -1 : 1);
        b.spin.x += (idleX - b.spin.x) * 0.02;
        b.spin.y += (idleY - b.spin.y) * 0.02;
        if (Math.abs(b.spin.y) > 0.01) anyMoving = true;
      });
      renderer.render(scene, cam);
      if (!stage.classList.contains("is-live")) stage.classList.add("is-live");
      // 움직임을 줄이는 설정이면 정지 화면 한 장만 그린다
      if (reduce && !anyMoving && !drag) { running = false; return; }
      requestAnimationFrame(tick);
    }
    if (reduce) balls.forEach(function (b) { b.y = R; });
    wake();
  }
})();
