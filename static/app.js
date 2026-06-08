const state = {
  catalog: null,
  theme: "全部",
  assetType: "全部",
  search: "",
  selectedId: null,
  charts: {},
};

const els = {
  updateStatus: document.getElementById("updateStatus"),
  generatedAt: document.getElementById("generatedAt"),
  refreshButton: document.getElementById("refreshButton"),
  kpiGrid: document.getElementById("kpiGrid"),
  searchInput: document.getElementById("searchInput"),
  themeFilters: document.getElementById("themeFilters"),
  rankList: document.getElementById("rankList"),
  mediaWall: document.getElementById("mediaWall"),
  themeMap: document.getElementById("themeMap"),
  companyList: document.getElementById("companyList"),
  detailPanel: document.getElementById("detailPanel"),
  tablePreview: document.getElementById("tablePreview"),
  assetTypeFilters: document.getElementById("assetTypeFilters"),
  assetTable: document.getElementById("assetTable"),
};

const typeLabels = {
  word: "Word",
  pdf: "PDF",
  video: "视频",
  image: "图片",
  csv: "CSV",
  excel: "Excel",
};

const typeIcons = {
  word: "file-text",
  pdf: "presentation",
  video: "video",
  image: "image",
  csv: "table",
  excel: "sheet",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatBytes(bytes) {
  if (!bytes) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function scoreOf(company, key = "综合评分") {
  return Number(company?.scores?.[key] ?? 0);
}

function normalizedText(...parts) {
  return parts.join(" ").toLowerCase();
}

function visibleCompanies() {
  const catalog = state.catalog;
  if (!catalog) return [];
  const query = state.search.trim().toLowerCase();
  return catalog.companies.filter((company) => {
    const themeOk = state.theme === "全部" || company.theme === state.theme;
    if (!themeOk) return false;
    if (!query) return true;
    const haystack = normalizedText(
      company.name,
      company.title,
      company.ticker,
      company.theme,
      company.summary,
      company.assets?.map((asset) => asset.title).join(" ")
    );
    return haystack.includes(query);
  });
}

async function loadCatalog() {
  setStatus("正在读取数据...");
  try {
    const response = await fetch("/api/catalog", { cache: "no-store" });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return await response.json();
  } catch (error) {
    const response = await fetch("data/catalog.json", { cache: "no-store" });
    if (!response.ok) throw error;
    return await response.json();
  }
}

function setStatus(text, error = false) {
  els.updateStatus.textContent = text;
  els.updateStatus.classList.toggle("error", error);
}

function render() {
  const catalog = state.catalog;
  if (!catalog) return;
  setStatus(catalog.warning || "数据已就绪");
  els.generatedAt.textContent = `更新时间：${formatDate(catalog.generated_at)}`;
  renderKpis();
  renderThemeFilters();
  renderAssetTypeFilters();
  renderRankList();
  renderMediaWall();
  renderThemeMap();
  renderCompanyList();
  ensureSelection();
  renderCharts();
  renderAssetTable();
  if (window.lucide) lucide.createIcons();
}

function renderKpis() {
  const stats = state.catalog.stats || {};
  const cards = [
    ["资料文件", stats.file_count ?? 0],
    ["覆盖公司", stats.company_count ?? 0],
    ["研究主题", stats.theme_count ?? 0],
    ["资料体量", formatBytes(stats.total_size_bytes ?? 0)],
  ];
  els.kpiGrid.innerHTML = cards
    .map(([label, value]) => `<div class="kpi"><small>${label}</small><strong>${value}</strong></div>`)
    .join("");
}

function renderThemeFilters() {
  const themes = ["全部", ...state.catalog.themes.map((theme) => theme.name)];
  els.themeFilters.innerHTML = themes
    .map(
      (theme) =>
        `<button type="button" class="${theme === state.theme ? "active" : ""}" data-theme="${escapeHtml(theme)}">${escapeHtml(
          theme
        )}</button>`
    )
    .join("");
  els.themeFilters.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.theme = button.dataset.theme;
      state.selectedId = null;
      render();
    });
  });
}

function renderAssetTypeFilters() {
  const typeCounts = state.catalog.stats?.file_type_counts || {};
  const types = ["全部", ...Object.keys(typeCounts).sort()];
  els.assetTypeFilters.innerHTML = types
    .map((type) => {
      const label = type === "全部" ? "全部" : typeLabels[type] || type.toUpperCase();
      const count = type === "全部" ? state.catalog.assets.length : typeCounts[type];
      return `<button type="button" class="${type === state.assetType ? "active" : ""}" data-type="${escapeHtml(type)}">${escapeHtml(
        label
      )} ${count}</button>`;
    })
    .join("");
  els.assetTypeFilters.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.assetType = button.dataset.type;
      renderAssetTable();
      if (window.lucide) lucide.createIcons();
    });
  });
}

function renderRankList() {
  const companies = visibleCompanies().slice().sort((a, b) => scoreOf(b) - scoreOf(a));
  if (!companies.length) {
    els.rankList.innerHTML = `<div class="empty-state">没有匹配的公司或专题</div>`;
    return;
  }
  els.rankList.innerHTML = companies
    .map(
      (company, index) => `
        <button class="rank-item" type="button" data-id="${escapeHtml(company.id)}">
          <span class="rank-num">${index + 1}</span>
          <span>
            <span class="item-title">${escapeHtml(displayName(company))}</span>
            <span class="item-subtitle">${escapeHtml(company.theme)} · ${escapeHtml(company.ticker || "专题")}</span>
          </span>
          <span class="score-pill">${scoreOf(company).toFixed(1)}</span>
        </button>
      `
    )
    .join("");
  els.rankList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => selectCompany(button.dataset.id, true));
  });
}

function renderMediaWall() {
  const media = state.catalog.assets.filter((asset) => ["image", "video"].includes(asset.type)).slice(0, 9);
  if (!media.length) {
    els.mediaWall.innerHTML = `<div class="empty-state">暂无图片或视频资产</div>`;
    return;
  }
  els.mediaWall.innerHTML = media
    .map((asset) => {
      const label = escapeHtml(asset.title);
      if (asset.type === "image") {
        return `<a class="media-thumb" href="${asset.url}" target="_blank" rel="noreferrer"><img src="${asset.url}" alt="${label}" loading="lazy"><span>${label}</span></a>`;
      }
      return `<a class="media-thumb" href="${asset.url}" target="_blank" rel="noreferrer"><video src="${asset.url}" muted playsinline preload="metadata"></video><span>${label}</span></a>`;
    })
    .join("");
}

function renderThemeMap() {
  els.themeMap.innerHTML = state.catalog.themes
    .map((theme) => {
      const counts = Object.entries(theme.asset_types || {})
        .map(([type, count]) => `<span class="chip">${escapeHtml(typeLabels[type] || type)} ${count}</span>`)
        .join("");
      return `
        <article class="theme-card">
          <div>
            <h3>${escapeHtml(theme.name)}</h3>
            <p>${escapeHtml(theme.summary || "该主题已收录报告、演示稿与相关媒体资料。")}</p>
          </div>
          <div class="theme-stats">
            <span class="chip">公司 ${theme.company_count}</span>
            <span class="chip">报告 ${theme.report_count}</span>
            <span class="chip">资产 ${theme.asset_count}</span>
            ${counts}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderCompanyList() {
  const companies = visibleCompanies().slice().sort((a, b) => scoreOf(b) - scoreOf(a));
  els.companyList.innerHTML = companies
    .map(
      (company) => `
        <button class="company-button ${company.id === state.selectedId ? "active" : ""}" type="button" data-id="${escapeHtml(company.id)}">
          <span class="item-title">${escapeHtml(displayName(company))}</span>
          <span class="item-subtitle">${escapeHtml(company.theme)} · ${escapeHtml(company.ticker || "专题")} · 综合 ${scoreOf(company).toFixed(1)}</span>
        </button>
      `
    )
    .join("");
  els.companyList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => selectCompany(button.dataset.id, false));
  });
}

function ensureSelection() {
  const companies = visibleCompanies();
  if (!companies.length) {
    els.detailPanel.innerHTML = `<div class="empty-state">请选择其他主题或搜索词</div>`;
    renderTablePreview(null);
    return;
  }
  if (!state.selectedId || !companies.some((company) => company.id === state.selectedId)) {
    state.selectedId = companies[0].id;
  }
  renderDetail(selectedCompany());
}

function selectedCompany() {
  return state.catalog.companies.find((company) => company.id === state.selectedId) || null;
}

function selectCompany(id, scrollToDetail) {
  state.selectedId = id;
  renderCompanyList();
  renderDetail(selectedCompany());
  if (scrollToDetail) {
    document.getElementById("companies").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (window.lucide) lucide.createIcons();
}

function displayName(company) {
  if (company.ticker) return `${company.name} (${company.ticker})`;
  return company.title || company.name;
}

function renderDetail(company) {
  if (!company) return;
  const metricHtml = (company.metrics || [])
    .slice(0, 8)
    .map(
      (metric) => `
        <div class="metric-tile">
          <small>${escapeHtml(metric.label)}</small>
          <strong>${escapeHtml(metric.value || "-")}</strong>
        </div>
      `
    )
    .join("");
  const scoreHtml = Object.entries(company.scores || {})
    .map(
      ([label, value]) => `
        <div class="score-tile">
          <small>${escapeHtml(label)}</small>
          <strong>${Number(value).toFixed(1)}</strong>
        </div>
      `
    )
    .join("");
  const assetHtml = (company.assets || [])
    .map((asset) => assetLink(asset))
    .join("");
  const video = (company.assets || []).find((asset) => asset.type === "video");
  const image = (company.assets || []).find((asset) => asset.type === "image");
  const mediaHtml = video
    ? `<video class="detail-media" src="${video.url}" controls preload="metadata"></video>`
    : image
      ? `<img class="detail-media" src="${image.url}" alt="${escapeHtml(image.title)}" loading="lazy">`
      : "";
  const points = listHtml(company.key_points);
  const risks = listHtml(company.risks);
  const sections = sectionHtml(company.sections);

  els.detailPanel.innerHTML = `
    <div class="detail-top">
      <div>
        <div class="detail-meta">
          <span class="chip">${escapeHtml(company.theme)}</span>
          <span class="chip">${escapeHtml(company.ticker || "专题")}</span>
          <span class="chip">资产 ${company.assets?.length || 0}</span>
        </div>
        <h3>${escapeHtml(displayName(company))}</h3>
        <p class="detail-summary">${escapeHtml(company.summary || "该条目已收录资料，但 Word 中没有抽取到可用摘要。")}</p>
      </div>
      <div class="score-pill">${scoreOf(company).toFixed(1)}</div>
    </div>
    <div class="score-grid">${scoreHtml}</div>
    ${metricHtml ? `<div class="metric-grid">${metricHtml}</div>` : ""}
    ${assetHtml ? `<div class="detail-block"><h4>资料入口</h4><div class="asset-links">${assetHtml}</div></div>` : ""}
    ${mediaHtml ? `<div class="detail-block">${mediaHtml}</div>` : ""}
    <div class="detail-columns">
      <div class="detail-block"><h4>核心信息</h4>${points}</div>
      <div class="detail-block"><h4>风险与约束</h4>${risks}</div>
    </div>
    ${sections ? `<div class="detail-block"><h4>报告章节</h4>${sections}</div>` : ""}
  `;
  renderTablePreview(company);
}

function assetLink(asset) {
  const icon = typeIcons[asset.type] || "file";
  const label = typeLabels[asset.type] || asset.type.toUpperCase();
  return `<a href="${asset.url}" target="_blank" rel="noreferrer"><i data-lucide="${icon}"></i>${escapeHtml(label)}</a>`;
}

function listHtml(items) {
  if (!items || !items.length) return `<p class="detail-summary">暂无抽取结果。</p>`;
  return `<ul>${items.slice(0, 7).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function sectionHtml(sections) {
  if (!sections || !sections.length) return "";
  return sections
    .slice(0, 8)
    .map(
      (section, index) => `
        <details ${index === 0 ? "open" : ""}>
          <summary>${escapeHtml(section.title)}</summary>
          <p class="detail-summary">${escapeHtml(section.body)}</p>
        </details>
      `
    )
    .join("");
}

function renderCharts() {
  renderScoreBubbleChart();
  renderThemeAssetChart();
}

function destroyChart(id) {
  if (state.charts[id]) {
    state.charts[id].destroy();
    state.charts[id] = null;
  }
}

function renderScoreBubbleChart() {
  const canvas = document.getElementById("scoreBubbleChart");
  if (!canvas || !window.Chart) return;
  destroyChart("scoreBubbleChart");
  const companies = state.catalog.companies.filter((company) => company.ticker);
  state.charts.scoreBubbleChart = new Chart(canvas, {
    type: "bubble",
    data: {
      datasets: [
        {
          label: "公司评分",
          data: companies.map((company) => ({
            x: scoreOf(company, "增长质量"),
            y: scoreOf(company, "AI暴露度"),
            r: Math.max(7, scoreOf(company) / 4),
            company,
          })),
          backgroundColor: "rgba(31, 122, 224, 0.58)",
          borderColor: "#1f7ae0",
          hoverBackgroundColor: "rgba(22, 155, 114, 0.72)",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => displayName(items[0].raw.company),
            label: (item) => [
              `增长质量：${scoreOf(item.raw.company, "增长质量").toFixed(1)}`,
              `AI 暴露度：${scoreOf(item.raw.company, "AI暴露度").toFixed(1)}`,
              `综合评分：${scoreOf(item.raw.company).toFixed(1)}`,
            ],
          },
        },
      },
      scales: {
        x: { min: 0, max: 100, title: { display: true, text: "增长质量" } },
        y: { min: 0, max: 100, title: { display: true, text: "AI 暴露度" } },
      },
      onClick: (_event, elements) => {
        const element = elements[0];
        if (!element) return;
        const raw = state.charts.scoreBubbleChart.data.datasets[element.datasetIndex].data[element.index];
        selectCompany(raw.company.id, true);
      },
    },
    plugins: [chartLabelPlugin()],
  });
}

function chartLabelPlugin() {
  return {
    id: "companyLabels",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.font = "700 11px Inter, sans-serif";
      ctx.fillStyle = "#172033";
      ctx.textAlign = "center";
      chart.data.datasets[0].data.forEach((point, index) => {
        const meta = chart.getDatasetMeta(0).data[index];
        if (!meta) return;
        ctx.fillText(point.company.ticker || point.company.name.slice(0, 8), meta.x, meta.y - point.r - 7);
      });
      ctx.restore();
    },
  };
}

function renderThemeAssetChart() {
  const canvas = document.getElementById("themeAssetChart");
  if (!canvas || !window.Chart) return;
  destroyChart("themeAssetChart");
  const themes = state.catalog.themes;
  const types = ["word", "pdf", "video", "image", "csv", "excel"];
  const colors = ["#1f7ae0", "#169b72", "#7457d9", "#b87500", "#cf3e4f", "#657184"];
  state.charts.themeAssetChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: themes.map((theme) => theme.name),
      datasets: types.map((type, index) => ({
        label: typeLabels[type] || type,
        data: themes.map((theme) => Number(theme.asset_types?.[type] || 0)),
        backgroundColor: colors[index],
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { stacked: true },
        y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
      },
      plugins: {
        legend: { position: "bottom" },
      },
    },
  });
}

function renderTablePreview(company) {
  let table = null;
  let title = "";
  if (company?.tables?.length) {
    table = company.tables.find((item) => item.is_financial) || company.tables[0];
    title = `${displayName(company)} · 表格 ${table.index}`;
  }
  if (!table) {
    const tabular = state.catalog.tabular_assets?.[0];
    if (tabular?.preview?.rows) {
      table = { headers: tabular.preview.columns, rows: tabular.preview.rows };
      title = tabular.title;
    } else if (tabular?.preview?.sheets) {
      const [sheetName, sheet] = Object.entries(tabular.preview.sheets)[0] || [];
      if (sheet) {
        table = { headers: sheet.columns, rows: sheet.rows };
        title = `${tabular.title} · ${sheetName}`;
      }
    }
  }
  if (!table) {
    els.tablePreview.innerHTML = `<div class="empty-state">暂无可预览表格</div>`;
    return;
  }
  els.tablePreview.innerHTML = `
    <p class="detail-summary">${escapeHtml(title)}</p>
    <table>
      <thead><tr>${(table.headers || []).map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
      <tbody>
        ${(table.rows || [])
          .slice(0, 12)
          .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`)
          .join("")}
      </tbody>
    </table>
  `;
}

function renderAssetTable() {
  const query = state.search.trim().toLowerCase();
  const assets = state.catalog.assets.filter((asset) => {
    const typeOk = state.assetType === "全部" || asset.type === state.assetType;
    const themeOk = state.theme === "全部" || asset.theme === state.theme;
    if (!typeOk || !themeOk) return false;
    if (!query) return true;
    return normalizedText(asset.title, asset.theme, asset.ticker, asset.relative_path).includes(query);
  });
  els.assetTable.innerHTML = assets
    .map(
      (asset) => `
        <tr>
          <td>${escapeHtml(asset.title)}</td>
          <td>${escapeHtml(typeLabels[asset.type] || asset.type)}</td>
          <td>${escapeHtml(asset.theme)}</td>
          <td>${escapeHtml(asset.ticker || "-")}</td>
          <td>${formatBytes(asset.size_bytes)}</td>
          <td><a class="open-link" href="${asset.url}" target="_blank" rel="noreferrer"><i data-lucide="${typeIcons[asset.type] || "file"}"></i>打开</a></td>
        </tr>
      `
    )
    .join("");
  if (!assets.length) {
    els.assetTable.innerHTML = `<tr><td colspan="6"><div class="empty-state">没有匹配的资料</div></td></tr>`;
  }
}

async function rebuildCatalog() {
  els.refreshButton.disabled = true;
  setStatus("正在更新资料，文件较多时需要一点时间...");
  try {
    const response = await fetch("/api/rebuild", { method: "POST" });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || payload.stderr || "更新失败");
    }
    setStatus(`更新完成：${payload.files} 个文件，${payload.companies} 家公司`);
    state.catalog = await loadCatalog();
    render();
  } catch (error) {
    setStatus(`更新失败：${error.message}`, true);
  } finally {
    els.refreshButton.disabled = false;
    if (window.lucide) lucide.createIcons();
  }
}

async function boot() {
  els.searchInput.addEventListener("input", () => {
    state.search = els.searchInput.value;
    state.selectedId = null;
    render();
  });
  els.refreshButton.addEventListener("click", rebuildCatalog);
  try {
    state.catalog = await loadCatalog();
    render();
  } catch (error) {
    setStatus(`读取失败：${error.message}`, true);
    els.detailPanel.innerHTML = `<div class="empty-state">请先运行后端或生成 catalog.json。</div>`;
  }
  if (window.lucide) lucide.createIcons();
}

boot();

window.addEventListener("load", () => {
  if (!state.catalog) return;
  renderCharts();
  if (window.lucide) lucide.createIcons();
});
