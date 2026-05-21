// Minimal entity graph renderer. Uses canvas + plain JS — no external
// vis library dep (keeps the project lean). Lays nodes out with a
// quick force-ish iteration, draws nodes + edges, labels.

async function renderGraph(type, depth) {
  const root = document.getElementById("entity-graph");
  if (!root) return;
  const r = await fetch(`/api/entities-graph?type=${type}&depth=${depth}`);
  const g = await r.json();

  const W = root.clientWidth || 800;
  const H = 480;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  c.style.background = "#0c0e12";
  c.style.border = "1px solid #262b35";
  c.style.borderRadius = "6px";
  root.innerHTML = "";
  root.appendChild(c);
  const ctx = c.getContext("2d");

  // Initial layout: nodes on a circle.
  const nodes = g.nodes.map((n, i) => ({
    ...n,
    x: W/2 + Math.cos(i * 2 * Math.PI / g.nodes.length) * Math.min(W,H)/3,
    y: H/2 + Math.sin(i * 2 * Math.PI / g.nodes.length) * Math.min(W,H)/3,
    vx: 0, vy: 0,
  }));
  const byId = Object.fromEntries(nodes.map(n => [n.id, n]));

  // Spring-mass-ish iteration. Cheap.
  for (let step = 0; step < 200; step++) {
    // Repulsion between all pairs.
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = dx*dx + dy*dy + 0.01;
        const f = 800 / d2;
        const ux = dx / Math.sqrt(d2), uy = dy / Math.sqrt(d2);
        a.vx += ux * f; a.vy += uy * f;
        b.vx -= ux * f; b.vy -= uy * f;
      }
    }
    // Spring along edges.
    for (const e of g.edges) {
      const a = byId[e.src_id], b = byId[e.dst_id];
      if (!a || !b) continue;
      const dx = b.x - a.x, dy = b.y - a.y;
      const d = Math.sqrt(dx*dx + dy*dy) + 0.01;
      const f = (d - 120) * 0.04;
      const ux = dx / d, uy = dy / d;
      a.vx += ux * f; a.vy += uy * f;
      b.vx -= ux * f; b.vy -= uy * f;
    }
    // Integrate.
    for (const n of nodes) {
      n.x += n.vx * 0.1; n.y += n.vy * 0.1;
      n.vx *= 0.8; n.vy *= 0.8;
      n.x = Math.max(40, Math.min(W - 40, n.x));
      n.y = Math.max(40, Math.min(H - 40, n.y));
    }
  }

  // Draw edges.
  ctx.strokeStyle = "#2f6a51";
  ctx.lineWidth = 1;
  for (const e of g.edges) {
    const a = byId[e.src_id], b = byId[e.dst_id];
    if (!a || !b) continue;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }

  // Draw nodes.
  for (const n of nodes) {
    const color = typeColor(n.type);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(n.x, n.y, 8, 0, 2 * Math.PI);
    ctx.fill();
    ctx.fillStyle = "#e6e8ec";
    ctx.font = "11px -apple-system, sans-serif";
    ctx.fillText(n.name.slice(0, 22), n.x + 10, n.y + 4);
  }

  // Click handler.
  c.addEventListener("click", (ev) => {
    const rect = c.getBoundingClientRect();
    const x = ev.clientX - rect.left, y = ev.clientY - rect.top;
    for (const n of nodes) {
      if ((n.x - x)**2 + (n.y - y)**2 < 100) {
        window.location = `/entities/${n.id}`;
        return;
      }
    }
  });
}

function typeColor(t) {
  const m = {
    Service: "#5cd7a0", Repo: "#74c0ff", Person: "#f0c674",
    DataStore: "#ff6e7e", CloudAccount: "#b48eff", Vendor: "#ffa500",
    Control: "#5cd7a0", Policy: "#9aa1ab", Runbook: "#74c0ff",
    Endpoint: "#ff6e7e",
  };
  return m[t] || "#9aa1ab";
}
