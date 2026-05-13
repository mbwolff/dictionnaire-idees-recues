/* ══════════════════════════════════════════════════════════════════
   app.js — Dictionnaire des idées reçues
   ══════════════════════════════════════════════════════════════════ */

/* ── State ─────────────────────────────────────────────────────────── */
const state = {
  lang:          "fr",
  searchMode:    "text",
  currentView:   "browse",
  currentEntry:  null,
  page:          1,
  pageSize:      40,
  totalEntries:  0,
  searchQuery:   "",
  searchDebounce: null,
  clusters:      [],
};

const i18n = {
  fr: {
    flaubert:        "Flaubert",
    generated:       "Généré",
    similarity:      "Similarité",
    neighbours:      "Entrées voisines",
    seeAlso:         "Voir aussi",
    results:         "résultats pour",
    noResults:       "Aucun résultat.",
    addLoading:      "Génération en cours…",
    addExists:       "Cette entrée existe déjà.",
    addSuccess:      "Entrée créée.",
    addError:        "Erreur",
    statsFlaubert:   "entrées originales",
    statsGenerated:  "entrées générées",
    browse:          "Parcourir",
    themes:          "Thèmes",
    addEntry:        "Ajouter",
    loadMore:        "Charger plus",
    searchPlaceholder: "Chercher une entrée…",
    addPlaceholder:  "Ex : CINÉMA, TOURISME…",
    addDesc:         "Entrez un nom commun ou propre en français. L'entrée sera vérifiée, puis générée dans le style de Flaubert.",
    searchHint:      "Sélectionnez une entrée ou effectuez une recherche.",
    allEntries:      "Toutes les entrées",
    semanticThemes:  "Thèmes sémantiques",
    newEntry:        "Nouvelle entrée",
    generatedEntries:"Entrées générées",
    noGenerated:     "Aucune entrée générée.",
    generateBtn:     "Générer l'entrée",
  },
  en: {
    flaubert:        "Flaubert",
    generated:       "Generated",
    similarity:      "Similarity",
    neighbours:      "Neighbouring entries",
    seeAlso:         "See also",
    results:         "results for",
    noResults:       "No results found.",
    addLoading:      "Generating…",
    addExists:       "This entry already exists.",
    addSuccess:      "Entry created.",
    addError:        "Error",
    statsFlaubert:   "original entries",
    statsGenerated:  "generated entries",
    browse:          "Browse",
    themes:          "Themes",
    addEntry:        "Add entry",
    loadMore:        "Load more",
    searchPlaceholder: "Search an entry…",
    addPlaceholder:  "E.g. CINÉMA, TOURISME…",
    addDesc:         "Enter a French noun (common or proper). It will be validated, then generated in Flaubert's style.",
    searchHint:      "Select an entry or search above.",
    allEntries:      "All entries",
    semanticThemes:  "Semantic themes",
    newEntry:        "New entry",
    generatedEntries:"Generated entries",
    noGenerated:     "No generated entries yet.",
    generateBtn:     "Generate entry",
  },
};

/* ── DOM refs ──────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const el = {
  searchInput:    $("search-input"),
  pillText:       $("pill-text"),
  pillSemantic:   $("pill-semantic"),
  entryList:      $("entry-list"),
  entryCount:     $("entry-count"),
  alphaIndex:     $("alpha-index"),
  loadMore:       $("load-more"),
  clusterList:    $("cluster-list"),
  generatedList:  $("generated-list"),
  addInput:       $("add-input"),
  addBtn:         $("add-btn"),
  addStatus:      $("add-status"),
  addBtnText:     $("add-btn-text"),
  welcomeState:   $("welcome-state"),
  entryDetail:    $("entry-detail"),
  searchResults:  $("search-results"),
  statsRow:       $("stats-row"),
  langBtn:        $("lang-btn"),
  langLabel:      $("lang-label"),
  themeBtn:       $("theme-btn"),
};

/* ── API ───────────────────────────────────────────────────────────── */
async function api(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/* ── Language & theme ─────────────────────────────────────────────── */
function toggleLang() {
  state.lang = state.lang === "fr" ? "en" : "fr";
  el.langLabel.textContent = state.lang === "fr" ? "EN" : "FR";
  applyTranslations();
  refreshAll();
}

function applyTranslations() {
  const t = i18n[state.lang];
  document.querySelectorAll("[data-fr]").forEach(node => {
    node.textContent = state.lang === "fr" ? node.dataset.fr : node.dataset.en;
  });
  el.searchInput.placeholder = t.searchPlaceholder;
  el.addInput.placeholder    = t.addPlaceholder;
  el.addBtnText.textContent  = t.generateBtn;
}

let darkMode = window.matchMedia("(prefers-color-scheme: dark)").matches;
function toggleTheme() {
  darkMode = !darkMode;
  document.documentElement.dataset.theme = darkMode ? "dark" : "";
}
document.documentElement.dataset.theme = darkMode ? "dark" : "";

/* ── Views ─────────────────────────────────────────────────────────── */
function switchView(view) {
  state.currentView = view;
  document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".sidebar-panel").forEach(p => p.classList.remove("active"));
  $(`nav-${view}`).classList.add("active");
  $(`panel-${view}`).classList.add("active");
}

/* ── Entry list ────────────────────────────────────────────────────── */
function renderEntryList(entries, append = false) {
  if (!append) el.entryList.innerHTML = "";
  const t = i18n[state.lang];

  if (!entries.length && !append) {
    el.entryList.innerHTML = `<p class="empty-state">${t.noResults}</p>`;
    return;
  }

  entries.forEach(entry => {
    const btn = document.createElement("button");
    btn.className = "list-entry" + (entry.is_generated ? " generated" : "");
    btn.dataset.headword = entry.headword;
    btn.textContent = entry.headword;
    if (entry.is_generated) {
      const tag = document.createElement("span");
      tag.className = "entry-list-tag";
      tag.textContent = "✦";
      btn.appendChild(tag);
    }
    btn.addEventListener("click", () => loadEntry(entry.headword));
    el.entryList.appendChild(btn);
  });
}

function buildAlphaIndex() {
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
  el.alphaIndex.innerHTML = "";
  letters.forEach(l => {
    const btn = document.createElement("button");
    btn.className = "alpha-btn";
    btn.textContent = l;
    btn.addEventListener("click", () => jumpToLetter(l));
    el.alphaIndex.appendChild(btn);
  });
}

function jumpToLetter(letter) {
  el.searchInput.value = letter;
  state.searchQuery = letter;
  doSearch(letter);
}

async function loadBrowsePage(append = false) {
  if (!append) { state.page = 1; }
  const start = (state.page - 1) * state.pageSize;
  try {
    const data = await api(`/api/search?limit=${state.pageSize}&page=${state.page}&lang=${state.lang}`);
    state.totalEntries = data.total;
    el.entryCount.textContent = data.total;
    renderEntryList(data.results, append);
    el.loadMore.style.display = data.results.length < state.pageSize ? "none" : "block";
    el.loadMore.textContent = i18n[state.lang].loadMore;
  } catch (e) {
    el.entryList.innerHTML = `<p class="empty-state">Error loading entries.</p>`;
  }
}

/* ── Search ────────────────────────────────────────────────────────── */
function doSearch(q) {
  if (!q) {
    showView("welcome");
    loadBrowsePage();
    return;
  }
  const url = `/api/search?q=${encodeURIComponent(q)}&mode=${state.searchMode}&lang=${state.lang}&limit=30`;
  api(url).then(data => {
    showView("results");
    renderSearchResults(q, data.results);
    // Also filter sidebar
    renderEntryList(data.results.slice(0, 60));
  }).catch(err => {
    console.error(err);
  });
}

function renderSearchResults(q, results) {
  const t = i18n[state.lang];
  $("results-title").textContent = q;
  $("results-count").textContent = `${results.length} ${t.results} "${q}"`;

  const list = $("results-list");
  if (!results.length) {
    list.innerHTML = `<p class="empty-state">${t.noResults}</p>`;
    return;
  }

  list.innerHTML = results.map(entry => {
    const hw = entry.headword;
    const text = entry.text_translated || entry.text || "";
    const preview = text.length > 120 ? text.slice(0, 120) + "…" : text;
    return `
      <div class="result-card" onclick="loadEntry('${hw.replace(/'/g, "\\'")}')">
        <div class="result-headword">${highlight(hw, q)}</div>
        <div class="result-text">${preview}</div>
        <div class="result-meta">
          <span class="cluster-badge">${entry.cluster_label || ""}</span>
          <span class="source-badge ${entry.is_generated ? 'generated' : 'flaubert'}">
            ${entry.is_generated ? t.generated : t.flaubert}
          </span>
        </div>
      </div>`;
  }).join("");
}

function highlight(text, q) {
  if (!q) return text;
  const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return text.replace(re, "<mark>$1</mark>");
}

/* ── Entry detail ──────────────────────────────────────────────────── */
async function loadEntry(headword) {
  // Mark active in sidebar
  document.querySelectorAll(".list-entry").forEach(b => {
    b.classList.toggle("active", b.dataset.headword === headword);
  });

  try {
    const entry = await api(`/api/entry/${encodeURIComponent(headword)}?lang=${state.lang}`);
    state.currentEntry = entry;
    renderEntryDetail(entry);
    showView("entry");
  } catch (e) {
    console.error("Entry not found:", headword, e);
  }
}

function renderEntryDetail(entry) {
  const t = i18n[state.lang];

  $("detail-headword").textContent = entry.headword;
  const tr = entry.headword_translated && entry.headword_translated !== entry.headword
    ? `(${entry.headword_translated})` : "";
  $("detail-headword-tr").textContent = tr;

  $("detail-cluster").textContent = entry.cluster_label || "";
  const srcBadge = $("detail-source");
  srcBadge.textContent = entry.is_generated ? t.generated : t.flaubert;
  srcBadge.className = `source-badge ${entry.is_generated ? "generated" : "flaubert"}`;

  // Text
  $("detail-text-fr").textContent = entry.text || "";
  const enEl = $("detail-text-en");
  if (state.lang === "en" && entry.text_translated && entry.text_translated !== entry.text) {
    enEl.textContent = entry.text_translated;
    enEl.style.display = "block";
  } else {
    enEl.style.display = "none";
  }

  // Tags
  const tagsEl = $("detail-tags");
  tagsEl.innerHTML = (entry.tag_labels || [])
    .map(t => `<span class="entry-tag">${t}</span>`)
    .join("");

  // Cross-references
  const xrefsWrap = $("detail-xrefs-wrap");
  if (entry.xrefs && entry.xrefs.length) {
    $("detail-xrefs").innerHTML = entry.xrefs
      .map(x => `<span class="xref-link" onclick="loadEntry('${x}')">${x}</span>`)
      .join("");
    $("xrefs-label").textContent = t.seeAlso;
    xrefsWrap.style.display = "block";
  } else {
    xrefsWrap.style.display = "none";
  }

  // Neighbours
  const nbSection = $("neighbours-section");
  const nbGrid    = $("neighbours-grid");
  if (entry.neighbours && entry.neighbours.length) {
    $("neighbours-title").textContent = t.neighbours;
    nbGrid.innerHTML = entry.neighbours.map(n => `
      <div class="neighbour-card" onclick="loadEntry('${n.headword.replace(/'/g, "\\'")}')">
        <div class="neighbour-hw">${n.headword}</div>
        <div class="neighbour-text">${n.text_translated || n.text || ""}</div>
        <div class="neighbour-sim">${t.similarity}: ${(n.similarity * 100).toFixed(0)}%</div>
      </div>`).join("");
    nbSection.style.display = "block";
  } else {
    nbSection.style.display = "none";
  }
}

/* ── Views switch ──────────────────────────────────────────────────── */
function showView(view) {
  el.welcomeState.style.display  = view === "welcome" ? "block" : "none";
  el.entryDetail.style.display   = view === "entry"   ? "block" : "none";
  el.searchResults.style.display = view === "results" ? "block" : "none";
}

/* ── Clusters ──────────────────────────────────────────────────────── */
async function loadClusters() {
  try {
    state.clusters = await api(`/api/clusters?lang=${state.lang}`);
    renderClusters();
  } catch (e) { el.clusterList.innerHTML = `<p class="empty-state">Error.</p>`; }
}

function renderClusters() {
  el.clusterList.innerHTML = state.clusters.map(c => `
    <div class="cluster-item" onclick="filterByCluster(${c.cluster_id})">
      <div>
        <span class="cluster-label">${c.label}</span>
        <span class="cluster-count">${c.count}</span>
      </div>
      <div class="cluster-tags">${(c.top_tags || []).map(t => `<span class="cluster-tag">${t}</span>`).join("")}</div>
      <div class="cluster-samples">${(c.sample_headwords || []).join(" · ")}</div>
    </div>`).join("");
}

async function filterByCluster(clusterId) {
  switchView("browse");
  // Search using cluster label as query for now (real filtering via cluster_id would need API extension)
  const cluster = state.clusters.find(c => c.cluster_id === clusterId);
  if (cluster && cluster.sample_headwords.length) {
    el.searchInput.value = "";
    loadBrowsePage();
  }
}

/* ── Add / Generate ────────────────────────────────────────────────── */
async function generateEntry() {
  const word = el.addInput.value.trim();
  if (!word) return;
  const t = i18n[state.lang];

  el.addBtn.disabled = true;
  el.addStatus.style.display = "block";
  el.addStatus.className = "add-status loading";
  el.addStatus.textContent = t.addLoading;

  try {
    const result = await apiPost("/api/generate", { word, lang: state.lang });

    if (result.error) {
      el.addStatus.className = "add-status error";
      el.addStatus.textContent = result.error;
    } else if (result.already_exists) {
      el.addStatus.className = "add-status";
      el.addStatus.textContent = t.addExists;
      loadEntry(result.headword);
    } else {
      el.addStatus.className = "add-status success";
      el.addStatus.textContent = t.addSuccess;
      el.addInput.value = "";
      loadGeneratedList();
      loadEntry(result.headword);
      switchView("browse");
      loadBrowsePage();
    }
  } catch (e) {
    el.addStatus.className = "add-status error";
    el.addStatus.textContent = `${t.addError}: ${e.message}`;
  } finally {
    el.addBtn.disabled = false;
  }
}

async function loadGeneratedList() {
  try {
    const data = await api(`/api/search?lang=${state.lang}&limit=50`);
    const generated = data.results.filter(e => e.is_generated);
    const t = i18n[state.lang];
    if (!generated.length) {
      el.generatedList.innerHTML = `<p class="empty-state">${t.noGenerated}</p>`;
      return;
    }
    el.generatedList.innerHTML = "";
    generated.forEach(entry => {
      const btn = document.createElement("button");
      btn.className = "list-entry generated";
      btn.dataset.headword = entry.headword;
      btn.textContent = entry.headword;
      btn.addEventListener("click", () => loadEntry(entry.headword));
      el.generatedList.appendChild(btn);
    });
  } catch (e) { console.error(e); }
}

/* ── Stats ─────────────────────────────────────────────────────────── */
async function loadStats() {
  try {
    const stats = await api("/api/stats");
    const t = i18n[state.lang];
    el.statsRow.innerHTML = `
      <div class="stat-item">
        <span class="stat-value">${stats.flaubert_entries}</span>
        <span class="stat-label">${t.statsFlaubert}</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">${stats.generated_entries}</span>
        <span class="stat-label">${t.statsGenerated}</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">${stats.clusters}</span>
        <span class="stat-label">clusters</span>
      </div>`;
  } catch (e) { el.statsRow.innerHTML = ""; }
}

/* ── Refresh ────────────────────────────────────────────────────────── */
function refreshAll() {
  applyTranslations();
  loadBrowsePage();
  loadClusters();
  loadStats();
  loadGeneratedList();
  if (state.currentEntry) renderEntryDetail(state.currentEntry);
  if (state.searchQuery) doSearch(state.searchQuery);
}

/* ── Event listeners ───────────────────────────────────────────────── */
el.langBtn.addEventListener("click", toggleLang);
el.themeBtn.addEventListener("click", toggleTheme);

el.pillText.addEventListener("click", () => {
  state.searchMode = "text";
  el.pillText.classList.add("active");
  el.pillSemantic.classList.remove("active");
  if (state.searchQuery) doSearch(state.searchQuery);
});

el.pillSemantic.addEventListener("click", () => {
  state.searchMode = "semantic";
  el.pillSemantic.classList.add("active");
  el.pillText.classList.remove("active");
  if (state.searchQuery) doSearch(state.searchQuery);
});

el.searchInput.addEventListener("input", e => {
  const q = e.target.value.trim();
  state.searchQuery = q;
  clearTimeout(state.searchDebounce);
  state.searchDebounce = setTimeout(() => doSearch(q), 280);
});

document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => {
    switchView(btn.dataset.view);
    if (btn.dataset.view === "add") loadGeneratedList();
  });
});

el.loadMore.addEventListener("click", () => {
  state.page++;
  loadBrowsePage(true);
});

el.addBtn.addEventListener("click", generateEntry);

el.addInput.addEventListener("keydown", e => {
  if (e.key === "Enter") generateEntry();
});

/* ── Init ───────────────────────────────────────────────────────────── */
function init() {
  buildAlphaIndex();
  loadBrowsePage();
  loadClusters();
  loadStats();
  showView("welcome");
  applyTranslations();
}

init();
