// 場面の絵の共通の道具（scripts/場面.mjs で撮る）。同じ t なら必ず同じ絵になるよう、乱数は種つき。
const W = 720, H = 1280;
const cv = document.getElementById('c');
const g = cv.getContext('2d');

function 乱数(seed) {  // mulberry32
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// なめらかなゆらぎ（0〜1）。k をずらすと別のゆらぎ
function ゆらぎ(t, k = 0) {
  return 0.5 + 0.25 * Math.sin(t * 7.1 + k * 1.7) + 0.15 * Math.sin(t * 12.3 + k * 4.1) + 0.1 * Math.sin(t * 19.7 + k * 2.3);
}

function 縦グラデ(y0, y1, stops) {
  const gr = g.createLinearGradient(0, y0, 0, y1);
  stops.forEach(([p, c]) => gr.addColorStop(p, c));
  return gr;
}

// 山なみ：seed で形を決め、base の高さに、amp の起伏で描く
function 山(seed, base, amp, color) {
  const r = 乱数(seed);
  const pts = [];
  for (let x = -40; x <= W + 40; x += 40) pts.push([x, base - amp * (0.4 + 0.6 * r())]);
  g.beginPath();
  g.moveTo(-40, H);
  pts.forEach(([x, y], i) => {
    if (i === 0) g.lineTo(x, y);
    else {
      const [px, py] = pts[i - 1];
      g.quadraticCurveTo(px, py, (px + x) / 2, (py + y) / 2);
    }
  });
  g.lineTo(W + 40, H);
  g.closePath();
  g.fillStyle = color;
  g.fill();
}

// 舞い落ちる紅葉
function 紅葉(t, n, seed, area = [0, W, 300, H]) {
  const r = 乱数(seed);
  const colors = ['#d9482b', '#e8873a', '#f2b33d', '#c0392b'];
  for (let i = 0; i < n; i++) {
    const x0 = area[0] + r() * (area[1] - area[0]);
    const speed = 40 + r() * 50;
    const y = area[2] + ((r() * (area[3] - area[2]) + t * speed) % (area[3] - area[2]));
    const x = x0 + 30 * Math.sin(t * (0.8 + r()) + i);
    const rot = t * (1 + r() * 2) + i;
    const s = 7 + r() * 7;
    g.save();
    g.translate(x, y);
    g.rotate(rot);
    g.fillStyle = colors[i % colors.length];
    g.beginPath();
    for (let k = 0; k < 5; k++) {  // 5つの先のある葉
      const a = (k / 5) * Math.PI * 2 - Math.PI / 2;
      g.lineTo(Math.cos(a) * s, Math.sin(a) * s);
      const b = a + Math.PI / 5;
      g.lineTo(Math.cos(b) * s * 0.45, Math.sin(b) * s * 0.45);
    }
    g.closePath();
    g.fill();
    g.restore();
  }
}

// ゆっくり寄る（scale を t で）
function 寄る(t, sec = 5, z = 0.05, cx = W / 2, cy = H * 0.7) {
  const s = 1 + z * (t / sec);
  g.translate(cx, cy);
  g.scale(s, s);
  g.translate(-cx, -cy);
}
