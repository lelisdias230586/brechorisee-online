const $report = (sel) => document.querySelector(sel);

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function setupCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(320, rect.width) * ratio;
  canvas.height = Number(canvas.getAttribute("height") || 220) * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  return { ctx, width: canvas.width / ratio, height: canvas.height / ratio };
}

function drawEmpty(ctx, width, height, text) {
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = cssVar("--muted") || "#777";
  ctx.font = "14px system-ui";
  ctx.textAlign = "center";
  ctx.fillText(text, width / 2, height / 2);
}

function shortLabel(value, max = 14) {
  const text = String(value || "");
  return text.length > max ? text.slice(0, max - 1) + "…" : text;
}

function drawLineChart(canvas, labels, values, formatter) {
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);

  if (!values.some(v => Number(v) > 0)) {
    drawEmpty(ctx, width, height, "Sem dados no período");
    return;
  }

  const pad = 34;
  const max = Math.max(...values.map(Number), 1);
  const accent = cssVar("--accent") || "#a84d3a";
  const muted = cssVar("--muted") || "#777";
  const line = cssVar("--line") || "#ddd";

  ctx.strokeStyle = line;
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad + ((height - pad * 2) * i / 4);
    ctx.beginPath();
    ctx.moveTo(pad, y);
    ctx.lineTo(width - pad, y);
    ctx.stroke();
  }

  ctx.strokeStyle = accent;
  ctx.lineWidth = 3;
  ctx.beginPath();
  values.forEach((value, i) => {
    const x = pad + ((width - pad * 2) * i / Math.max(1, values.length - 1));
    const y = height - pad - ((Number(value) / max) * (height - pad * 2));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = accent;
  values.forEach((value, i) => {
    const x = pad + ((width - pad * 2) * i / Math.max(1, values.length - 1));
    const y = height - pad - ((Number(value) / max) * (height - pad * 2));
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
  });

  ctx.fillStyle = muted;
  ctx.font = "12px system-ui";
  ctx.textAlign = "left";
  ctx.fillText(formatter(max), pad, 16);
  ctx.textAlign = "right";
  ctx.fillText(labels[labels.length - 1]?.slice(5).split("-").reverse().join("/") || "", width - pad, height - 8);
}

function drawBarChart(canvas, labels, values, formatter, options = {}) {
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);

  if (!values.some(v => Number(v) > 0)) {
    drawEmpty(ctx, width, height, "Sem dados no período");
    return;
  }

  const pad = 34;
  const max = Math.max(...values.map(Number), 1);
  const accent = cssVar("--accent") || "#a84d3a";
  const muted = cssVar("--muted") || "#777";
  const barArea = width - pad * 2;
  const visible = labels.slice(0, options.limit || labels.length);
  const vals = values.slice(0, visible.length);
  const gap = Math.max(5, Math.min(10, 80 / visible.length));
  const barWidth = Math.max(10, (barArea / visible.length) - gap);

  vals.forEach((value, i) => {
    const x = pad + i * (barWidth + gap);
    const h = (Number(value) / max) * (height - pad * 2);
    const y = height - pad - h;
    ctx.fillStyle = accent;
    ctx.globalAlpha = .82;
    ctx.fillRect(x, y, barWidth, h);
    ctx.globalAlpha = 1;
  });

  ctx.fillStyle = muted;
  ctx.font = "11px system-ui";
  ctx.textAlign = "center";
  visible.forEach((label, i) => {
    const x = pad + i * (barWidth + gap) + barWidth / 2;
    if (i % Math.ceil(visible.length / 8) === 0 || visible.length <= 8) {
      ctx.save();
      ctx.translate(x, height - 8);
      ctx.rotate(-0.45);
      ctx.fillText(shortLabel(label, 12), 0, 0);
      ctx.restore();
    }
  });
  ctx.textAlign = "left";
  ctx.fillText(formatter(max), pad, 16);
}

function renderSupplierBars(items) {
  const box = $report("#supplierBars");
  if (!items.length) {
    box.innerHTML = "<p class='hint'>Sem fornecedoras no período.</p>";
    return;
  }
  const max = Math.max(...items.map(item => Number(item.cost_total || 0)), 1);
  box.innerHTML = items.map(item => {
    const percent = Math.max(4, Number(item.cost_total || 0) / max * 100);
    return `
      <div class="bar-item">
        <div>
          <strong>${item.supplier}</strong>
          <small>${item.entries} entrada(s) • vendido ${brl(item.sold_total)}</small>
        </div>
        <div class="bar-track"><span style="width:${percent}%"></span></div>
        <b>${brl(item.cost_total)}</b>
      </div>
    `;
  }).join("");
}

function renderTable(selector, headers, rows, emptyText = "Sem dados no período.") {
  const box = $report(selector);
  if (!box) return;
  if (!rows || !rows.length) {
    box.innerHTML = `<p class="hint">${emptyText}</p>`;
    return;
  }
  box.innerHTML = `
    <div class="table-scroll">
      <table>
        <thead><tr>${headers.map(h => `<th>${h}</th>`).join("")}</tr></thead>
        <tbody>${rows.join("")}</tbody>
      </table>
    </div>
  `;
}

function renderCustomerPreferences(items) {
  const grouped = new Map();
  items.forEach(item => {
    if (!grouped.has(item.customer)) grouped.set(item.customer, []);
    grouped.get(item.customer).push(item);
  });
  const rows = Array.from(grouped.entries()).map(([customer, prefs]) => {
    const prefText = prefs.map(p => `${p.preference} (${p.qty})`).join(" • ");
    const total = prefs.reduce((sum, p) => sum + Number(p.total || 0), 0);
    return `<tr><td><strong>${customer}</strong></td><td>${prefText}</td><td>${brl(total)}</td></tr>`;
  });
  renderTable("#customerPreferences", ["Cliente", "Estilos preferidos", "Total"], rows, "Ainda não há preferências suficientes.");
}

function renderTopCustomers(items) {
  const rows = items.map((item, i) => `
    <tr>
      <td>${i + 1}</td>
      <td><strong>${item.customer}</strong></td>
      <td>${item.purchases}</td>
      <td>${brl(item.total)}</td>
      <td>${brl(item.avg_ticket)}</td>
    </tr>
  `);
  renderTable("#topCustomersTable", ["#", "Cliente", "Compras", "Total", "Ticket médio"], rows, "Nenhum cliente no período.");
}

function renderCashierSummary(summary) {
  const rows = [
    ["Vendas", summary.sales_qty || 0],
    ["Peças vendidas", summary.items_sold || 0],
    ["Faturamento", brl(summary.total)],
    ["Descontos", brl(summary.discounts)],
    ["Ticket médio", brl(summary.avg_ticket)],
    ["Margem bruta", `${brl(summary.gross_margin)} (${Number(summary.gross_margin_pct || 0).toFixed(1)}%)`],
    ["Valor em estoque disponível", brl(summary.stock_value)],
    ["Custo/repasse em estoque", brl(summary.stock_cost)],
  ].map(row => `<tr><td><strong>${row[0]}</strong></td><td>${row[1]}</td></tr>`);
  renderTable("#cashierSummary", ["Indicador", "Valor"], rows);
}

async function loadReports() {
  const days = $report("#reportDays").value;
  const res = await fetch(`/api/reports?days=${encodeURIComponent(days)}`);
  const data = await res.json();

  const salesValues = data.sales.map(item => Number(item.total || 0));
  const purchaseValues = data.purchases.map(item => Number(item.total || 0));
  const summary = data.cashier_summary || {};

  $report("#salesTotal").textContent = brl(salesValues.reduce((a, b) => a + b, 0));
  $report("#purchaseTotal").textContent = brl(purchaseValues.reduce((a, b) => a + b, 0));
  $report("#kpiSales").textContent = brl(summary.total);
  $report("#kpiItems").textContent = String(summary.items_sold || 0);
  $report("#kpiAvg").textContent = brl(summary.avg_ticket);
  $report("#kpiMargin").textContent = brl(summary.gross_margin);
  $report("#kpiMarginPct").textContent = `${Number(summary.gross_margin_pct || 0).toFixed(1)}% de margem`;

  drawLineChart($report("#salesChart"), data.labels, salesValues, brl);
  drawLineChart($report("#purchaseChart"), data.labels, purchaseValues, brl);

  drawBarChart($report("#monthChart"), data.monthly_sales.map(i => i.month), data.monthly_sales.map(i => Number(i.total || 0)), brl, { limit: 18 });
  drawBarChart($report("#paymentChart"), data.payment_methods.map(i => i.label), data.payment_methods.map(i => Number(i.total || 0)), brl);
  drawBarChart($report("#customerChart"), data.top_customers.map(i => i.customer), data.top_customers.map(i => Number(i.total || 0)), brl);
  drawBarChart($report("#topChart"), data.top_sales.map(i => i.label), data.top_sales.map(i => Number(i.total || 0)), brl);

  const ageLabels = Object.keys(data.age_buckets);
  const ageValues = Object.values(data.age_buckets);
  drawBarChart($report("#ageChart"), ageLabels, ageValues, value => `${Math.round(value)} peças`);

  drawBarChart($report("#weekChart"), data.day_of_week.map(i => i.label), data.day_of_week.map(i => Number(i.total || 0)), brl);
  drawBarChart($report("#hourChart"), data.hour_sales.map(i => i.label), data.hour_sales.map(i => Number(i.total || 0)), brl, { limit: 24 });

  drawBarChart($report("#portfolioCategoryChart"), data.portfolio_category.map(i => i.label), data.portfolio_category.map(i => Number(i.qty || 0)), v => `${Math.round(v)} peças`);
  drawBarChart($report("#portfolioBrandChart"), data.portfolio_brand.map(i => i.label), data.portfolio_brand.map(i => Number(i.qty || 0)), v => `${Math.round(v)} peças`);
  drawBarChart($report("#portfolioColorChart"), data.portfolio_color.map(i => i.label), data.portfolio_color.map(i => Number(i.qty || 0)), v => `${Math.round(v)} peças`);
  drawBarChart($report("#portfolioSizeChart"), data.portfolio_size.map(i => i.label), data.portfolio_size.map(i => Number(i.qty || 0)), v => `${Math.round(v)} peças`);

  renderCustomerPreferences(data.customer_preferences || []);
  renderTopCustomers(data.top_customers || []);
  renderSupplierBars(data.suppliers || []);
  renderCashierSummary(summary);
}

document.addEventListener("DOMContentLoaded", () => {
  $report("#reportDays").addEventListener("change", loadReports);
  window.addEventListener("resize", () => {
    clearTimeout(window.__brechoReportResize);
    window.__brechoReportResize = setTimeout(loadReports, 150);
  });
  loadReports();
});
