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
  searchQuery:        "",
  searchDebounce:     null,
  typeaheadDebounce:  null,
  typeaheadIdx:       -1,
  clusters:           [],
  highlightedCluster: null,
  showSecondary:      false,
  showGenerated:      false,
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
    suggestBtn:      "Suggérer un thème",
    suggestHint:     (label, members) => `Le thème <strong>${label}</strong> est peu représenté — entrées voisines : ${members}.`,
    copyDone:        "Copié !",
    didYouMean:      "Peut-être :",
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
    suggestBtn:      "Suggest a topic",
    suggestHint:     (label, members) => `The theme <strong>${label}</strong> is underrepresented — related entries: ${members}.`,
    copyDone:        "Copied!",
    didYouMean:      "Did you mean:",
  },
};

/* ── DOM refs ──────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const el = {
  searchInput:    $("search-input"),
  typeahead:      $("typeahead-dropdown"),
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
  suggestBtn:     $("suggest-btn"),
  suggestHint:    $("suggest-hint"),
  welcomeState:   $("welcome-state"),
  entryDetail:    $("entry-detail"),
  searchResults:  $("search-results"),
  statsRow:       $("stats-row"),
  langBtn:        $("lang-btn"),
  langLabel:      $("lang-label"),
  themeBtn:       $("theme-btn"),
  umapView:       $("umap-view"),
  umapSvg:        $("umap-svg"),
  umapLegend:     $("umap-legend"),
  umapTooltip:    $("umap-tooltip"),
  umapSearch:       $("umap-search"),
  umapGeneratedBtn: $("umap-generated-btn"),
  tagList:          $("tag-list"),
  statsView:        $("stats-view"),
  statsContent:     $("stats-content"),
  copyEntryBtn:     $("copy-entry-btn"),
  hamburgerBtn:     $("hamburger-btn"),
  sidebarBackdrop:  $("sidebar-backdrop"),
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
  el.suggestHint.style.display = "none";
  document.querySelectorAll(".pill[data-tip-fr]").forEach(p => {
    p.dataset.tip = state.lang === "fr" ? p.dataset.tipFr : p.dataset.tipEn;
  });
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
  el.searchInput.value = "";
  state.searchQuery = "";
  const url = `/api/search?q=${encodeURIComponent(letter)}&mode=prefix&lang=${state.lang}&limit=100`;
  api(url).then(data => {
    renderEntryList(data.results);
    el.loadMore.style.display = "none";
  }).catch(err => console.error(err));
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
    const hint = state.searchMode === "text"
      ? (state.lang === "fr"
          ? `<p class="empty-state">${t.noResults}</p><p class="empty-hint">Essayez la recherche <button class="empty-switch-btn" id="empty-switch-semantic">Sémantique</button> pour trouver des entrées de sens proche.</p>`
          : `<p class="empty-state">${t.noResults}</p><p class="empty-hint">Try <button class="empty-switch-btn" id="empty-switch-semantic">Semantic</button> search to find entries with similar meaning.</p>`)
      : `<p class="empty-state">${t.noResults}</p>`;
    list.innerHTML = hint;
    const switchBtn = $("empty-switch-semantic");
    if (switchBtn) {
      switchBtn.addEventListener("click", () => {
        state.searchMode = "semantic";
        el.pillSemantic.classList.add("active");
        el.pillText.classList.remove("active");
        doSearch(state.searchQuery);
      });
    }
    if (state.searchMode === "text" && q) {
      api(`/api/fuzzy?q=${encodeURIComponent(q)}`).then(suggestions => {
        if (!suggestions.length) return;
        const row = document.createElement("p");
        row.className = "empty-hint fuzzy-hint";
        row.innerHTML = `${t.didYouMean} ` + suggestions
          .map(hw => `<button class="empty-switch-btn fuzzy-suggestion" data-hw="${hw}">${hw}</button>`)
          .join(" · ");
        list.appendChild(row);
        list.querySelectorAll(".fuzzy-suggestion").forEach(btn => {
          btn.addEventListener("click", () => {
            el.searchInput.value = btn.dataset.hw;
            state.searchQuery = btn.dataset.hw;
            doSearch(btn.dataset.hw);
          });
        });
      }).catch(() => {});
    }
    return;
  }

  list.innerHTML = results.map((entry, i) => {
    const hw = entry.headword;
    const text = entry.text_translated || entry.text || "";
    const preview = text.length > 120 ? text.slice(0, 120) + "…" : text;
    return `
      <div class="result-card" data-idx="${i}">
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
  list.querySelectorAll(".result-card").forEach((card, i) => {
    card.addEventListener("click", () => loadEntry(results[i].headword));
  });
}

function highlight(text, q) {
  if (!q) return text;
  const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return text.replace(re, "<mark>$1</mark>");
}

/* ── Entry detail ──────────────────────────────────────────────────── */
async function loadEntry(headword, skipHistory = false) {
  document.querySelectorAll(".list-entry").forEach(b => {
    b.classList.toggle("active", b.dataset.headword === headword);
  });
  const hwUp = headword.toUpperCase();
  const sessionEntry = sessionEntries.find(e =>
    e.headword === hwUp || e.headword === headword ||
    (e.headword_en && (e.headword_en === hwUp || e.headword_en === headword))
  );
  if (sessionEntry) {
    const entry = adaptSessionEntry(sessionEntry);
    state.currentEntry = entry;
    renderEntryDetail(entry);
    showView("entry");
    if (!skipHistory)
      history.pushState({ type: "entry", headword }, "", "#entry/" + encodeURIComponent(headword));
    return;
  }
  try {
    const entry = await api(`/api/entry/${encodeURIComponent(headword)}?lang=${state.lang}`);
    state.currentEntry = entry;
    renderEntryDetail(entry);
    showView("entry");
    if (!skipHistory) {
      history.pushState({ type: "entry", headword }, "", "#entry/" + encodeURIComponent(headword));
    }
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

  const prevBtn = $("entry-prev-btn");
  const nextBtn = $("entry-next-btn");
  if (prevBtn) {
    prevBtn.style.display = entry.prev_headword ? "" : "none";
    prevBtn.onclick = entry.prev_headword ? () => loadEntry(entry.prev_headword) : null;
  }
  if (nextBtn) {
    nextBtn.style.display = entry.next_headword ? "" : "none";
    nextBtn.onclick = entry.next_headword ? () => loadEntry(entry.next_headword) : null;
  }

  const priLabel = entry.cluster_label || "";
  const priMult  = entry.primary_cluster_score
    ? ` ${(entry.primary_cluster_score * 12).toFixed(1)}×` : "";
  $("detail-cluster").textContent = priLabel + priMult;

  const mapBtn = $("show-on-map-btn");
  if (mapBtn) {
    mapBtn.onclick = () => showOnMap(entry.headword);
    mapBtn.style.display = entry.cluster_id >= 0 ? "" : "none";
  }

  const copyBtn = $("copy-entry-btn");
  if (copyBtn) {
    copyBtn.onclick = async () => {
      const text = `${entry.headword}. ${entry.text}`;
      await navigator.clipboard.writeText(text);
      const orig = copyBtn.textContent;
      copyBtn.textContent = i18n[state.lang].copyDone;
      setTimeout(() => { copyBtn.textContent = orig; }, 1500);
    };
  }

  const secBadge = $("detail-secondary-cluster");
  if (entry.show_secondary_cluster && entry.secondary_cluster_label) {
    const secMult = ` ${(entry.secondary_cluster_score * 12).toFixed(1)}×`;
    secBadge.textContent = entry.secondary_cluster_label + secMult;
    secBadge.style.display = "";
  } else {
    secBadge.style.display = "none";
  }
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

  // Tags — clickable, navigate to rhetoric view filtered by tag
  const tagsEl = $("detail-tags");
  tagsEl.innerHTML = (entry.tag_labels || [])
    .map((lbl, i) => `<span class="entry-tag" data-tag="${entry.tags[i]}" data-label="${lbl}">${lbl}</span>`)
    .join("");
  tagsEl.querySelectorAll(".entry-tag").forEach(span => {
    span.addEventListener("click", () => {
      switchView("rhetoric");
      filterByTag(span.dataset.tag, span.dataset.label);
    });
  });

  // Cross-references
  const xrefsWrap = $("detail-xrefs-wrap");
  const xrefsEl = $("detail-xrefs");
  if (entry.xrefs && entry.xrefs.length) {
    xrefsEl.innerHTML = entry.xrefs
      .map((x, i) => `<span class="xref-link" data-idx="${i}">${x}</span>`)
      .join("");
    xrefsEl.querySelectorAll(".xref-link").forEach((span, i) => {
      span.addEventListener("click", () => loadEntry(entry.xrefs[i]));
    });
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
    nbGrid.innerHTML = entry.neighbours.map((n, i) => `
      <div class="neighbour-card" data-idx="${i}">
        <div class="neighbour-hw">${n.headword}</div>
        <div class="neighbour-text">${n.text_translated || n.text || ""}</div>
        <div class="neighbour-sim">${t.similarity}: ${(n.similarity * 100).toFixed(0)}%</div>
      </div>`).join("");
    nbGrid.querySelectorAll(".neighbour-card").forEach((card, i) => {
      card.addEventListener("click", () => loadEntry(entry.neighbours[i].headword));
    });
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
  el.umapView.style.display      = view === "umap"    ? "flex"  : "none";
  el.statsView.style.display     = view === "stats"   ? "block" : "none";
  if (view !== "umap" && el.umapSearch) el.umapSearch.value = "";
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

function filterByCluster(clusterId) {
  switchView("browse");
  el.searchInput.value = "";
  state.searchQuery = "";
  const url = `/api/search?mode=cluster&cluster_id=${clusterId}&lang=${state.lang}&limit=200`;
  api(url).then(data => {
    renderEntryList(data.results);
    el.loadMore.style.display = "none";
  }).catch(err => console.error(err));
}

function filterByClusterSorted(clusterId) {
  switchView("browse");
  el.searchInput.value = "";
  state.searchQuery = "";
  const url = `/api/search?mode=cluster&cluster_id=${clusterId}&lang=${state.lang}&limit=200`;
  api(url).then(data => {
    const sorted = [...data.results].sort(
      (a, b) => (b.primary_cluster_score ?? 0) - (a.primary_cluster_score ?? 0)
    );
    renderEntryList(sorted);
    el.loadMore.style.display = "none";
  }).catch(err => console.error(err));
}

/* ── Add / Generate ────────────────────────────────────────────────── */
async function generateEntry() {
  const word = el.addInput.value.trim();
  if (!word) return;
  const t = i18n[state.lang];
  const hwUp = word.trim().toUpperCase();

  // Client-side duplicate check against session entries
  if (sessionEntries.some(e => e.headword === hwUp || (e.headword_en && e.headword_en === hwUp))) {
    el.addStatus.style.display = "block";
    el.addStatus.className = "add-status";
    el.addStatus.textContent = t.addExists;
    return;
  }

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
      sessionEntries.push(result);
      saveSessionEntries();
      renderSessionGroup();
      el.addStatus.className = "add-status success";
      el.addStatus.textContent = t.addSuccess;
      el.addInput.value = "";
      loadGeneratedList();
      loadEntry(result.headword);
    }
  } catch (e) {
    el.addStatus.className = "add-status error";
    el.addStatus.textContent = `${t.addError}: ${e.message}`;
  } finally {
    el.addBtn.disabled = false;
  }
}

function loadGeneratedList() {
  const t = i18n[state.lang];
  if (!sessionEntries.length) {
    el.generatedList.innerHTML = `<p class="empty-state">${t.noGenerated}</p>`;
    return;
  }
  el.generatedList.innerHTML = "";
  [...sessionEntries].reverse().slice(0, 10).forEach(entry => {
    const row = document.createElement("div");
    row.className = "generated-row";

    const btn = document.createElement("button");
    btn.className = "list-entry generated";
    btn.dataset.headword = entry.headword;
    btn.textContent = state.lang === "en" ? (entry.headword_en || entry.headword) : entry.headword;
    btn.addEventListener("click", () => loadEntry(entry.headword));

    const del = document.createElement("button");
    del.className = "delete-generated-btn";
    del.title = "Supprimer";
    del.textContent = "×";
    del.addEventListener("click", () => {
      sessionEntries = sessionEntries.filter(e => e.headword !== entry.headword);
      saveSessionEntries();
      loadGeneratedList();
      renderSessionGroup();
    });

    row.appendChild(btn);
    row.appendChild(del);
    el.generatedList.appendChild(row);
  });
}

/* ── Rhetorical tags ───────────────────────────────────────────────── */
async function loadTags() {
  try {
    const tags = await api(`/api/tags?lang=${state.lang}`);
    renderTags(tags);
  } catch (e) { el.tagList.innerHTML = `<p class="empty-state">Error.</p>`; }
}

function renderTags(tags) {
  el.tagList.innerHTML = tags.map((t, i) => `
    <div class="tag-item" data-idx="${i}">
      <span class="tag-label">${t.label}</span>
      <span class="tag-count">${t.count}</span>
    </div>`).join("");
  el.tagList.querySelectorAll(".tag-item").forEach((item, i) => {
    item.addEventListener("click", () => filterByTag(tags[i].tag, tags[i].label));
  });
}

function filterByTag(tag, label) {
  el.searchInput.value = "";
  state.searchQuery = "";
  const url = `/api/search?mode=tag&tag=${encodeURIComponent(tag)}&lang=${state.lang}&limit=500`;
  api(url).then(data => {
    showView("results");
    $("results-title").textContent = label;
    $("results-count").textContent = `${data.total} ${state.lang === "fr" ? "entrées" : "entries"}`;
    const list = $("results-list");
    list.innerHTML = data.results.map((entry, i) => {
      const hw = entry.headword;
      const text = entry.text_translated || entry.text || "";
      const preview = text.length > 120 ? text.slice(0, 120) + "…" : text;
      return `
        <div class="result-card" data-idx="${i}">
          <div class="result-headword">${hw}</div>
          <div class="result-text">${preview}</div>
          <div class="result-meta">
            <span class="cluster-badge">${entry.cluster_label || ""}</span>
          </div>
        </div>`;
    }).join("");
    list.querySelectorAll(".result-card").forEach((card, i) => {
      card.addEventListener("click", () => loadEntry(data.results[i].headword));
    });
  }).catch(err => console.error(err));
}

/* ── UMAP ─────────────────────────────────────────────────────────── */
const CLUSTER_PALETTE = [
  "#8b3a1a","#b8860b","#2e7d32","#1565c0","#6a1b9a",
  "#c0392b","#00695c","#1a5276","#7b241c","#4a7c59",
  "#0d47a1","#6d4c41",
];

let umapCache      = null;
let umapCircles    = new Map();   // headword → { cx, cy, color }
let umapTransform  = { tx: 0, ty: 0, k: 1 };
let umapScaleParams = null;  // { xMin, xMax, yMin, yMax, W, H, PAD }

let sessionEntries = JSON.parse(sessionStorage.getItem('dictionnaire_generated') || '[]');

function saveSessionEntries() {
  sessionStorage.setItem('dictionnaire_generated', JSON.stringify(sessionEntries));
}

function getUmapScale() {
  if (!umapScaleParams) return null;
  const { xMin, xMax, yMin, yMax, W, H, PAD } = umapScaleParams;
  return {
    sx: x => PAD + (x - xMin) / (xMax - xMin) * (W - 2 * PAD),
    sy: y => PAD + (y - yMin) / (yMax - yMin) * (H - 2 * PAD),
  };
}

function adaptSessionEntry(entry) {
  if (entry.lang === state.lang) return entry;
  return {
    ...entry,
    text_translated:      state.lang === "en" ? (entry.text_en || entry.text) : entry.text,
    headword_translated:  state.lang === "en" ? (entry.headword_en || entry.headword) : entry.headword,
    cluster_label:        entry.umap_cluster_label || entry.cluster_label,
    tag_labels:           [],
  };
}

async function loadUmap() {
  if (umapCache && umapCache.key === state.lang) {
    renderUmap(umapCache.points);
    return;
  }
  el.umapSvg.setAttribute("viewBox", "0 0 900 560");
  el.umapSvg.innerHTML = `<text x="450" y="280" text-anchor="middle"
    font-family="'IM Fell English SC',Georgia,serif" font-size="14"
    fill="var(--ink-muted)">Computing semantic map…</text>`;
  el.umapLegend.innerHTML = "";
  try {
    const points = await api(`/api/umap?lang=${state.lang}`);
    umapCache = { points, key: state.lang };
    renderUmap(points);
  } catch (e) {
    el.umapSvg.innerHTML = `<text x="450" y="280" text-anchor="middle"
      font-family="'IM Fell English SC',Georgia,serif" font-size="14"
      fill="var(--ink-muted)">Error loading visualization.</text>`;
  }
}

function applyUmapTransform() {
  const g = document.getElementById("umap-g");
  if (g) g.setAttribute("transform",
    `translate(${umapTransform.tx.toFixed(2)},${umapTransform.ty.toFixed(2)}) scale(${umapTransform.k.toFixed(4)})`);
}

function renderUmap(points) {
  const W = 900, H = 560, PAD = 28;
  const xs = points.map(p => p.x), ys = points.map(p => p.y);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const sx = x => PAD + (x - xMin) / (xMax - xMin) * (W - 2 * PAD);
  const sy = y => PAD + (y - yMin) / (yMax - yMin) * (H - 2 * PAD);
  umapScaleParams = { xMin, xMax, yMin, yMax, W, H, PAD };

  el.umapSvg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  el.umapSvg.innerHTML = "";
  el.umapSvg.classList.remove("highlight-active");
  umapCircles.clear();
  umapTransform = { tx: 0, ty: 0, k: 1 };

  const ns = "http://www.w3.org/2000/svg";
  const container = el.umapSvg.closest(".umap-container");

  // All drawn content lives in this group so pan/zoom only transforms it
  const g = document.createElementNS(ns, "g");
  g.id = "umap-g";
  el.umapSvg.appendChild(g);

  // Centroid accumulator
  const centroids = {};

  points.forEach(p => {
    const color = CLUSTER_PALETTE[p.cluster_id % CLUSTER_PALETTE.length] ?? "#888";
    const cx = sx(p.x).toFixed(1), cy = sy(p.y).toFixed(1);

    // Radius proportional to membership strength (2.5 baseline → ~6 max)
    const r0 = p.primary_cluster_score
      ? (2.5 + Math.max(0, (p.primary_cluster_score * 12 - 1) * 8)).toFixed(1)
      : "4";

    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", cx);
    c.setAttribute("cy", cy);
    c.setAttribute("r", r0);
    c.setAttribute("fill", color);
    c.setAttribute("stroke", "none");
    c.setAttribute("stroke-width", "0");
    c.style.opacity = "0.85";
    c.dataset.cluster = p.cluster_id;
    c.dataset.secondary = p.show_secondary_cluster ? "1" : "0";
    c.dataset.secondaryCluster = p.secondary_cluster_id ?? -1;
    c.style.cursor = "pointer";
    c.style.transition = "r 80ms, opacity 80ms";

    if (state.showSecondary && p.show_secondary_cluster) {
      const secColor = CLUSTER_PALETTE[(p.secondary_cluster_id ?? 0) % CLUSTER_PALETTE.length];
      c.setAttribute("stroke", secColor);
      c.setAttribute("stroke-width", "1.5");
    }

    const mult = p.primary_cluster_score
      ? ` · ${(p.primary_cluster_score * 12).toFixed(1)}×` : "";

    c.addEventListener("mouseenter", () => {
      const snippet = p.text_snippet ? `\n${p.text_snippet}` : "";
      el.umapTooltip.textContent = `${p.headword_display}\n${p.cluster_label}${mult}${snippet}`;
      el.umapTooltip.style.display = "block";
    });
    c.addEventListener("mousemove", e => {
      const rect = container.getBoundingClientRect();
      el.umapTooltip.style.left = (e.clientX - rect.left + 14) + "px";
      el.umapTooltip.style.top  = (e.clientY - rect.top  - 10) + "px";
    });
    c.addEventListener("mouseleave", () => {
      if (el.umapSvg.classList.contains("search-active")) {
        c.style.opacity = c.dataset.searchOpacity || "0.72";
      } else if (el.umapSvg.classList.contains("highlight-active")) {
        const isPri = c.dataset.cluster == state.highlightedCluster;
        const isSec = state.showSecondary && c.dataset.secondary === "1"
          && c.dataset.secondaryCluster == state.highlightedCluster;
        c.style.opacity = isPri ? "0.88" : isSec ? "0.45" : "0.10";
      } else {
        c.style.opacity = "0.72";
      }
      el.umapTooltip.style.display = "none";
    });
    c.addEventListener("click", () => {
      c.setAttribute("r", (+r0 + 2.5).toFixed(1));
      c.style.opacity = "1";
      c.parentNode.appendChild(c);
      loadEntry(p.headword); showView("entry");
    });

    g.appendChild(c);
    umapCircles.set(p.headword, { cx: +cx, cy: +cy, color, el: c });

    // Accumulate centroid
    if (p.cluster_id >= 0) {
      if (!centroids[p.cluster_id]) centroids[p.cluster_id] = { sumX: 0, sumY: 0, n: 0, label: p.cluster_label };
      centroids[p.cluster_id].sumX += +cx;
      centroids[p.cluster_id].sumY += +cy;
      centroids[p.cluster_id].n++;
    }
  });

  // Centroid labels
  Object.entries(centroids).forEach(([id, { sumX, sumY, n, label }]) => {
    const tx = (sumX / n).toFixed(1), ty = (sumY / n).toFixed(1);
    const abbrev = label.split(" & ")[0].trim().toUpperCase();
    const txt = document.createElementNS(ns, "text");
    txt.setAttribute("x", tx);
    txt.setAttribute("y", ty);
    txt.setAttribute("text-anchor", "middle");
    txt.setAttribute("dominant-baseline", "central");
    txt.setAttribute("font-size", "8");
    txt.setAttribute("font-family", "var(--font-ui)");
    txt.setAttribute("font-weight", "700");
    txt.setAttribute("letter-spacing", "0.06em");
    txt.setAttribute("fill", CLUSTER_PALETTE[+id % CLUSTER_PALETTE.length]);
    txt.setAttribute("opacity", "0.40");
    txt.setAttribute("pointer-events", "none");
    txt.setAttribute("data-centroid", id);
    txt.textContent = abbrev;
    g.appendChild(txt);
  });

  // Legend
  const clusters = {};
  points.forEach(p => { clusters[p.cluster_id] ??= p.cluster_label; });
  el.umapLegend.innerHTML = Object.entries(clusters)
    .sort((a, b) => +a[0] - +b[0])
    .map(([id, label]) => `
      <div class="umap-legend-item" data-cluster="${id}" onclick="highlightCluster(${id}); filterByClusterSorted(${id})">
        <span class="umap-legend-dot" style="background:${CLUSTER_PALETTE[+id % CLUSTER_PALETTE.length]}"></span>
        <span class="umap-legend-label">${label}</span>
      </div>`).join("");

  // Session-generated entries overlay (client-side, separate group)
  const sessionG = document.createElementNS(ns, "g");
  sessionG.id = "umap-session-g";
  sessionG.style.display = state.showGenerated ? "" : "none";
  g.appendChild(sessionG);
  renderSessionDots(sx, sy, sessionG);

  // Restore secondary toggle button state
  const secBtn = $("umap-secondary-btn");
  if (secBtn) secBtn.classList.toggle("active", state.showSecondary);

  applyTranslations();
}

function renderSessionDots(sx, sy, container) {
  const ns = "http://www.w3.org/2000/svg";
  const gold = "#c49a35";
  const umapContainer = el.umapSvg.closest(".umap-container");
  sessionEntries.forEach(entry => {
    if (!entry.umap_x || !entry.umap_y) return;
    const cx = sx(entry.umap_x).toFixed(1);
    const cy = sy(entry.umap_y).toFixed(1);
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", cx);
    c.setAttribute("cy", cy);
    c.setAttribute("r", "5");
    c.setAttribute("fill", "transparent");
    c.setAttribute("stroke", gold);
    c.setAttribute("stroke-width", "1.5");
    c.style.opacity = "0.85";
    c.style.cursor = "pointer";
    c.style.transition = "r 80ms, opacity 80ms";
    const label = entry.umap_cluster_label || entry.cluster_label || "";
    const snippet = entry.text_snippet ? `\n${entry.text_snippet}` : "";
    const display = state.lang === "en" ? (entry.headword_en || entry.headword) : entry.headword;
    c.addEventListener("mouseenter", () => {
      el.umapTooltip.textContent = `${display}\n${label}${snippet}`;
      el.umapTooltip.style.display = "block";
    });
    c.addEventListener("mousemove", e => {
      const rect = umapContainer.getBoundingClientRect();
      el.umapTooltip.style.left = (e.clientX - rect.left + 14) + "px";
      el.umapTooltip.style.top  = (e.clientY - rect.top  - 10) + "px";
    });
    c.addEventListener("mouseleave", () => {
      c.style.opacity = "0.72";
      el.umapTooltip.style.display = "none";
    });
    c.addEventListener("click", () => {
      c.setAttribute("r", "7.5");
      c.style.opacity = "1";
      c.parentNode.appendChild(c);
      loadEntry(entry.headword);
      showView("entry");
    });
    container.appendChild(c);
    umapCircles.set(entry.headword, { cx: +cx, cy: +cy, color: gold, el: c });
  });
}

function renderSessionGroup() {
  const sessionG = document.getElementById("umap-session-g");
  if (!sessionG || !umapScaleParams) return;
  sessionG.innerHTML = "";
  umapCircles.forEach((v, hw) => { if (sessionEntries.some(e => e.headword === hw)) umapCircles.delete(hw); });
  const scale = getUmapScale();
  if (scale) renderSessionDots(scale.sx, scale.sy, sessionG);
}

function highlightCluster(id) {
  const svg = el.umapSvg;
  if (state.highlightedCluster === id) {
    state.highlightedCluster = null;
    svg.classList.remove("highlight-active");
    svg.querySelectorAll("circle").forEach(c => c.style.opacity = "0.72");
    svg.querySelectorAll("text[data-centroid]").forEach(t => t.setAttribute("opacity", "0.40"));
    document.querySelectorAll(".umap-legend-item").forEach(i => i.classList.remove("active"));
  } else {
    state.highlightedCluster = id;
    svg.classList.add("highlight-active");
    svg.querySelectorAll("circle").forEach(c => {
      const isPri = c.dataset.cluster == id;
      const isSec = state.showSecondary && c.dataset.secondary === "1"
        && c.dataset.secondaryCluster == id;
      c.style.opacity = isPri ? "0.88" : isSec ? "0.45" : "0.10";
    });
    svg.querySelectorAll("text[data-centroid]").forEach(t => {
      t.setAttribute("opacity", t.getAttribute("data-centroid") == id ? "0.90" : "0.08");
    });
    document.querySelectorAll(".umap-legend-item").forEach(i => {
      i.classList.toggle("active", i.dataset.cluster == id);
    });
  }
}

function toggleSecondary() {
  state.showSecondary = !state.showSecondary;
  $("umap-secondary-btn").classList.toggle("active", state.showSecondary);
  el.umapSvg.querySelectorAll("circle[data-secondary='1']").forEach(c => {
    const sid = +c.dataset.secondaryCluster;
    c.setAttribute("stroke", state.showSecondary
      ? CLUSTER_PALETTE[sid % CLUSTER_PALETTE.length] : "none");
    c.setAttribute("stroke-width", state.showSecondary ? "1.5" : "0");
  });
}

function toggleGenerated() {
  state.showGenerated = !state.showGenerated;
  el.umapGeneratedBtn.classList.toggle("active", state.showGenerated);
  const sessionG = document.getElementById("umap-session-g");
  if (sessionG) sessionG.style.display = state.showGenerated ? "" : "none";
}

async function showOnMap(headword) {
  switchView("clusters");
  showView("umap");
  await loadUmap();
  el.umapSvg.querySelectorAll("circle").forEach(c => c.style.opacity = "0.72");
  const data = umapCircles.get(headword);
  if (!data) return;
  pulseAt(data.cx, data.cy, data.color);
}

function pulseAt(cx, cy, color) {
  const ns = "http://www.w3.org/2000/svg";
  for (let i = 0; i < 3; i++) {
    setTimeout(() => {
      const ring = document.createElementNS(ns, "circle");
      ring.setAttribute("cx", cx);
      ring.setAttribute("cy", cy);
      ring.setAttribute("r", "5");
      ring.setAttribute("fill", "none");
      ring.setAttribute("stroke", color);
      ring.setAttribute("stroke-width", "2.5");
      ring.setAttribute("opacity", "0.9");
      ring.style.pointerEvents = "none";
      ring.style.transition = "r 700ms ease-out, opacity 700ms ease-out";
      (document.getElementById("umap-g") || el.umapSvg).appendChild(ring);
      requestAnimationFrame(() => requestAnimationFrame(() => {
        ring.setAttribute("r", "24");
        ring.setAttribute("opacity", "0");
      }));
      setTimeout(() => ring.remove(), 750);
    }, i * 350);
  }
}

/* ── Random entry ───────────────────────────────────────────────────── */
async function loadRandom() {
  try {
    const entry = await api(`/api/random?lang=${state.lang}`);
    state.currentEntry = entry;
    renderEntryDetail(entry);
    showView("entry");
    history.pushState({ type: "entry", headword: entry.headword }, "", "#entry/" + encodeURIComponent(entry.headword));
  } catch (e) { console.error("Random entry failed:", e); }
}

/* ── Detailed stats + xref network ─────────────────────────────────── */
let statsCache = null;

async function loadDetailedStats() {
  if (statsCache && statsCache.lang === state.lang) { renderStatsView(statsCache.data, statsCache.xdata); return; }
  el.statsContent.innerHTML = `<div class="loading-state"><span class="loading-dot"></span></div>`;
  try {
    const [data, xdata] = await Promise.all([
      api(`/api/stats/detailed?lang=${state.lang}`),
      api(`/api/xrefs?lang=${state.lang}`),
    ]);
    statsCache = { lang: state.lang, data, xdata };
    renderStatsView(data, xdata);
  } catch (e) { el.statsContent.innerHTML = `<p class="empty-state">Error loading statistics.</p>`; }
}

function barChart(items, colorFn, labelKey = "label", valueKey = "count") {
  const BAR_MAX = 180, LABEL_W = 140, ROW_H = 16, PAD = 3;
  const maxVal = Math.max(...items.map(d => d[valueKey]), 1);
  const h = items.length * (ROW_H + PAD) + PAD;
  const rows = items.map((d, i) => {
    const bw = Math.max(1, (d[valueKey] / maxVal) * BAR_MAX);
    const y  = PAD + i * (ROW_H + PAD);
    const lbl = d[labelKey].length > 24 ? d[labelKey].slice(0, 22) + "…" : d[labelKey];
    return `<text x="${LABEL_W - 4}" y="${y + ROW_H * 0.72}" text-anchor="end" font-size="8.5" font-family="var(--font-ui)" fill="var(--ink-soft)">${lbl}</text>
<rect x="${LABEL_W}" y="${y}" width="${bw}" height="${ROW_H}" fill="${colorFn(d, i)}" rx="1" opacity="0.75"/>
<text x="${LABEL_W + bw + 4}" y="${y + ROW_H * 0.72}" font-size="8.5" font-family="var(--font-ui)" fill="var(--ink-faint)">${d[valueKey]}</text>`;
  }).join("");
  return `<svg width="${LABEL_W + BAR_MAX + 40}" height="${h}" overflow="visible">${rows}</svg>`;
}

const TAG_COLORS = ["#8b3a1a","#b8860b","#2e7d32","#1565c0","#6a1b9a","#c0392b","#00695c","#1a5276","#7b241c","#4a7c59","#0d47a1"];

function renderStatsView(data, xdata) {
  const t = i18n[state.lang];
  const tagSvg = barChart(data.tags, (_, i) => TAG_COLORS[i % TAG_COLORS.length]);
  const clsSvg = barChart(data.clusters, (d) => CLUSTER_PALETTE[d.cluster_id % CLUSTER_PALETTE.length]);

  el.statsContent.innerHTML = `
<div class="stats-page">
  <div class="stats-headline">
    <div class="stat-big"><span>${data.flaubert_entries}</span><br>${t.statsFlaubert}</div>
    <div class="stat-big"><span>${data.generated_entries}</span><br>${t.statsGenerated}</div>
    <div class="stat-big"><span>${data.dual_theme}</span><br>${state.lang === "fr" ? "thèmes ambigus" : "dual-theme"}</div>
    <div class="stat-big"><span>${data.xrefs.entries_with_xrefs}</span><br>${state.lang === "fr" ? "entrées avec renvois" : "entries with xrefs"}</div>
    <div class="stat-big"><span>${data.text_length.avg}</span><br>${state.lang === "fr" ? "car. moy. par entrée" : "avg chars / entry"}</div>
  </div>
  <div class="stats-charts">
    <div class="chart-block">
      <h3 class="chart-title">${state.lang === "fr" ? "Catégories rhétoriques" : "Rhetorical categories"}</h3>
      ${tagSvg}
    </div>
    <div class="chart-block">
      <h3 class="chart-title">${state.lang === "fr" ? "Répartition thématique" : "Thematic distribution"}</h3>
      ${clsSvg}
    </div>
  </div>
  <div class="xref-section">
    <h3 class="chart-title">${state.lang === "fr" ? "Réseau de renvois" : "Cross-reference network"}</h3>
    <p class="chart-sub">${data.xrefs.total_edges} ${state.lang === "fr" ? "liens · cliquez sur un nœud pour ouvrir l'entrée" : "links · click a node to open the entry"}</p>
    <svg id="xref-svg" class="xref-svg" preserveAspectRatio="xMidYMid meet"></svg>
  </div>
</div>`;

  // Populate sidebar summary
  const sum = $("stats-nav-summary");
  if (sum) sum.innerHTML = `
<div class="stats-nav-item"><span>${data.flaubert_entries}</span> ${t.statsFlaubert}</div>
<div class="stats-nav-item"><span>${data.generated_entries}</span> ${t.statsGenerated}</div>
<div class="stats-nav-item"><span>${data.xrefs.entries_with_xrefs}</span> ${state.lang === "fr" ? "avec renvois" : "with xrefs"}</div>`;

  if (xdata) renderXrefNetwork($("xref-svg"), xdata.nodes, xdata.edges);
}

function renderXrefNetwork(svgEl, nodes, edges) {
  if (!svgEl || !nodes.length) return;
  const W = 720, H = 400;
  const k = Math.sqrt(W * H / nodes.length) * 0.9;
  const ns = "http://www.w3.org/2000/svg";

  // Initialise in a circle — much better starting point than random scatter
  const r0 = Math.min(W, H) * 0.32;
  nodes.forEach((n, i) => {
    const a = (2 * Math.PI * i) / nodes.length;
    n.x = W / 2 + r0 * Math.cos(a);
    n.y = H / 2 + r0 * Math.sin(a);
    n.fx = 0; n.fy = 0;
  });

  const nodeIdx = new Map(nodes.map((n, i) => [n.id, i]));

  svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svgEl.innerHTML = "";

  // Arrowhead marker
  const defs = document.createElementNS(ns, "defs");
  defs.innerHTML = `<marker id="xref-arrow" markerWidth="6" markerHeight="4" refX="10" refY="2" orient="auto">
    <polygon points="0 0,6 2,0 4" fill="var(--ink-faint)" opacity="0.7"/></marker>`;
  svgEl.appendChild(defs);

  const edgeEls = edges.map(e => {
    const line = document.createElementNS(ns, "line");
    line.setAttribute("stroke", "var(--rule-heavy)");
    line.setAttribute("stroke-width", "1");
    line.setAttribute("marker-end", "url(#xref-arrow)");
    svgEl.appendChild(line);
    return line;
  });

  // Compute degree for each node
  const degree = new Map(nodes.map(n => [n.id, 0]));
  edges.forEach(e => {
    degree.set(e.source, (degree.get(e.source) || 0) + 1);
    degree.set(e.target, (degree.get(e.target) || 0) + 1);
  });
  const maxDeg = Math.max(...degree.values(), 1);

  const nodeEls = nodes.map(n => {
    const g = document.createElementNS(ns, "g");
    g.style.cursor = "pointer";
    const color = CLUSTER_PALETTE[(n.cluster_id >= 0 ? n.cluster_id : 0) % CLUSTER_PALETTE.length];
    const r = 4 + 6 * (degree.get(n.id) || 0) / maxDeg;
    const circ = document.createElementNS(ns, "circle");
    circ.setAttribute("r", r.toFixed(1)); circ.setAttribute("fill", color); circ.setAttribute("opacity", "0.85");
    g.appendChild(circ);
    const lbl = n.display.length > 14 ? n.display.slice(0, 13) + "…" : n.display;
    const txt = document.createElementNS(ns, "text");
    txt.setAttribute("text-anchor", "middle"); txt.setAttribute("dy", "-8");
    txt.setAttribute("font-size", "7.5"); txt.setAttribute("font-family", "var(--font-ui)");
    txt.setAttribute("fill", "var(--ink-soft)"); txt.setAttribute("pointer-events", "none");
    txt.textContent = lbl;
    g.appendChild(txt);
    g.addEventListener("click", () => { loadEntry(n.id); });
    svgEl.appendChild(g);
    return g;
  });

  // Spring-damper simulation: Coulomb repulsion + Hooke edge springs + gravity
  // FR repulsion (k²/d) falls off too slowly — gravity can't counter it for sparse graphs.
  // Inverse-square Coulomb (charge/d²) weakens fast enough that gravity dominates at distance.
  const charge = 1500;  // repulsion strength
  const springK = 0.12; // edge spring stiffness
  const restLen = 60;   // edge rest length (px)
  const grav = 0.04;    // gravity toward canvas centre
  const damp = 0.82;    // velocity damping per tick
  const maxV = 15;      // px/tick velocity cap

  nodes.forEach(n => { n.vx = 0; n.vy = 0; });
  let step = 0;
  const MAX = 350;

  function tick() {
    nodes.forEach(n => { n.fx = 0; n.fy = 0; });

    // Coulomb repulsion between every pair (inverse-square)
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[j].x - nodes[i].x, dy = nodes[j].y - nodes[i].y;
        const d2 = Math.max(dx * dx + dy * dy, 100); // floor at d=10
        const d = Math.sqrt(d2);
        const f = charge / d2;
        nodes[i].fx -= f * dx / d; nodes[i].fy -= f * dy / d;
        nodes[j].fx += f * dx / d; nodes[j].fy += f * dy / d;
      }
    }

    // Hooke's law spring along each edge
    edges.forEach(e => {
      const si = nodeIdx.get(e.source), ti = nodeIdx.get(e.target);
      if (si == null || ti == null) return;
      const dx = nodes[ti].x - nodes[si].x, dy = nodes[ti].y - nodes[si].y;
      const d = Math.max(Math.sqrt(dx * dx + dy * dy), 0.1);
      const f = springK * (d - restLen);
      nodes[si].fx += f * dx / d; nodes[si].fy += f * dy / d;
      nodes[ti].fx -= f * dx / d; nodes[ti].fy -= f * dy / d;
    });

    // Gravity toward canvas centre
    nodes.forEach(n => {
      n.fx += (W / 2 - n.x) * grav;
      n.fy += (H / 2 - n.y) * grav;
    });

    // Integrate: damp, cap, boundary-clamp
    nodes.forEach(n => {
      n.vx = Math.max(-maxV, Math.min(maxV, (n.vx + n.fx) * damp));
      n.vy = Math.max(-maxV, Math.min(maxV, (n.vy + n.fy) * damp));
      n.x = Math.max(30, Math.min(W - 30, n.x + n.vx));
      n.y = Math.max(20, Math.min(H - 20, n.y + n.vy));
    });

    // Update DOM
    nodeEls.forEach((g, i) => g.setAttribute("transform", `translate(${nodes[i].x.toFixed(1)},${nodes[i].y.toFixed(1)})`));
    edgeEls.forEach((line, i) => {
      const si = nodeIdx.get(edges[i].source), ti = nodeIdx.get(edges[i].target);
      if (si == null || ti == null) return;
      line.setAttribute("x1", nodes[si].x.toFixed(1)); line.setAttribute("y1", nodes[si].y.toFixed(1));
      line.setAttribute("x2", nodes[ti].x.toFixed(1)); line.setAttribute("y2", nodes[ti].y.toFixed(1));
    });
    if (++step < MAX) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
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
  statsCache = null;
  if (state.currentView === "rhetoric") loadTags();
  if (state.currentView === "stats")    { loadDetailedStats(); }
  if (state.currentEntry) loadEntry(state.currentEntry.headword, true);
  if (state.searchQuery) doSearch(state.searchQuery);
}

/* ── Event listeners ───────────────────────────────────────────────── */
el.langBtn.addEventListener("click", toggleLang);
el.themeBtn.addEventListener("click", toggleTheme);

$("home-btn").addEventListener("click", () => {
  el.searchInput.value = "";
  state.searchQuery = "";
  hideTypeahead();
  switchView("browse");
  showView("welcome");
  history.pushState({ type: "view", view: "browse" }, "", "#");
});

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
  hideTypeahead();
  if (state.searchQuery) doSearch(state.searchQuery);
});

el.searchInput.addEventListener("input", e => {
  const q = e.target.value.trim();
  state.searchQuery = q;
  clearTimeout(state.searchDebounce);
  state.searchDebounce = setTimeout(() => doSearch(q), 280);
  if (state.searchMode === "text" && q.length >= 1) {
    clearTimeout(state.typeaheadDebounce);
    state.typeaheadDebounce = setTimeout(() => updateTypeahead(q), 120);
  } else {
    hideTypeahead();
  }
});

el.searchInput.addEventListener("keydown", e => {
  const items = el.typeahead.querySelectorAll(".typeahead-item");
  if (!items.length || el.typeahead.style.display === "none") return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    state.typeaheadIdx = Math.min(state.typeaheadIdx + 1, items.length - 1);
    updateTypeaheadActive(items);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    state.typeaheadIdx = Math.max(state.typeaheadIdx - 1, -1);
    updateTypeaheadActive(items);
  } else if (e.key === "Enter" && state.typeaheadIdx >= 0) {
    e.preventDefault();
    items[state.typeaheadIdx].click();
  } else if (e.key === "Escape") {
    hideTypeahead();
  }
});

el.searchInput.addEventListener("blur", () => {
  setTimeout(hideTypeahead, 150);
});

function hideTypeahead() {
  el.typeahead.style.display = "none";
  state.typeaheadIdx = -1;
}

function updateTypeaheadActive(items) {
  items.forEach((it, i) => it.classList.toggle("active", i === state.typeaheadIdx));
}

async function updateTypeahead(q) {
  const results = await api(`/api/search?q=${encodeURIComponent(q)}&mode=prefix&lang=${state.lang}&limit=8`);
  if (!results.results || !results.results.length || el.searchInput.value.trim() !== q) {
    hideTypeahead(); return;
  }
  state.typeaheadIdx = -1;
  el.typeahead.innerHTML = results.results.map((r, i) =>
    `<div class="typeahead-item" data-idx="${i}">${r.headword}</div>`
  ).join("");
  el.typeahead.querySelectorAll(".typeahead-item").forEach((item, i) => {
    item.addEventListener("mousedown", () => {
      el.searchInput.value = "";
      hideTypeahead();
      loadEntry(results.results[i].headword);
    });
  });
  el.typeahead.style.display = "block";
}

document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => {
    const view = btn.dataset.view;
    switchView(view);
    if (view === "add")      { loadGeneratedList(); history.pushState({ type: "view", view }, "", "#add"); }
    if (view === "clusters") { showView("umap"); loadUmap(); history.pushState({ type: "view", view }, "", "#themes"); }
    if (view === "rhetoric") { loadTags(); history.pushState({ type: "view", view }, "", "#rhetoric"); }
    if (view === "stats")    { showView("stats"); loadDetailedStats(); history.pushState({ type: "view", view }, "", "#stats"); }
    if (view === "browse")   { history.pushState({ type: "view", view }, "", "#"); }
  });
});

$("random-btn").addEventListener("click", loadRandom);

el.loadMore.addEventListener("click", () => {
  state.page++;
  loadBrowsePage(true);
});

el.addBtn.addEventListener("click", generateEntry);

el.addInput.addEventListener("keydown", e => {
  if (e.key === "Enter") generateEntry();
});

el.suggestBtn.addEventListener("click", async () => {
  el.suggestBtn.disabled = true;
  try {
    const data = await api(`/api/suggest?lang=${state.lang}`);
    const t = i18n[state.lang];
    el.suggestHint.innerHTML = t.suggestHint(data.label, data.members.join(", "));
    el.suggestHint.style.display = "block";
  } catch (e) {
    console.error("Suggest failed:", e);
  } finally {
    el.suggestBtn.disabled = false;
  }
});

el.umapGeneratedBtn.addEventListener("click", toggleGenerated);

el.hamburgerBtn.addEventListener("click", () => {
  document.body.classList.toggle("sidebar-open");
});
el.sidebarBackdrop.addEventListener("click", () => {
  document.body.classList.remove("sidebar-open");
});
document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => document.body.classList.remove("sidebar-open"));
});

/* ── Keyboard shortcuts ─────────────────────────────────────────────── */
document.addEventListener("keydown", e => {
  const tag = document.activeElement.tagName;
  const inInput = tag === "INPUT" || tag === "TEXTAREA";
  if (e.key === "/" && !inInput) {
    e.preventDefault();
    el.searchInput.focus();
    el.searchInput.select();
  } else if (e.key === "Escape") {
    if (inInput) { document.activeElement.blur(); }
    else if (el.entryDetail.style.display !== "none") { showView("welcome"); }
  } else if (e.key === "r" && !inInput && !e.metaKey && !e.ctrlKey) {
    loadRandom();
  } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && !inInput) {
    const entry = state.currentEntry;
    if (!entry || el.entryDetail.style.display === "none") return;
    const hw = e.key === "ArrowLeft" ? entry.prev_headword : entry.next_headword;
    if (hw) loadEntry(hw);
  }
});

/* ── UMAP map search ───────────────────────────────────────────────── */
if (el.umapSearch) {
  el.umapSearch.addEventListener("input", e => {
    const q = e.target.value.trim().toUpperCase();
    if (!q) {
      el.umapSvg.classList.remove("search-active");
      el.umapSvg.querySelectorAll("circle").forEach(c => { c.style.opacity = "0.72"; delete c.dataset.searchOpacity; });
      return;
    }
    el.umapSvg.classList.add("search-active");
    let match = null;
    umapCircles.forEach((data, hw) => {
      const op = hw.includes(q) ? "1" : "0.08";
      data.el.style.opacity = op;
      data.el.dataset.searchOpacity = op;
      if (op === "1" && !match) match = data;
    });
    if (match) pulseAt(match.cx, match.cy, match.color);
  });
  el.umapSearch.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      el.umapSearch.value = "";
      el.umapSvg.classList.remove("search-active");
      el.umapSvg.querySelectorAll("circle").forEach(c => { c.style.opacity = "0.72"; delete c.dataset.searchOpacity; });
    }
  });
}

/* ── URL / browser history ──────────────────────────────────────────── */
window.addEventListener("popstate", e => {
  const s = e.state;
  if (!s) return;
  if (s.type === "entry") { loadEntry(s.headword, true); }
  else if (s.type === "view") {
    const v = s.view;
    switchView(v);
    if (v === "clusters") { showView("umap"); loadUmap(); }
    else if (v === "stats") { showView("stats"); loadDetailedStats(); }
    else if (v === "rhetoric") loadTags();
    else if (v === "add") loadGeneratedList();
  }
});

function handleInitialHash() {
  const hash = location.hash.slice(1);
  if (!hash || hash === "#") return;
  if (hash.startsWith("entry/")) {
    loadEntry(decodeURIComponent(hash.slice(6)), true);
  } else if (hash === "themes") {
    switchView("clusters"); showView("umap"); loadUmap();
  } else if (hash === "stats") {
    switchView("stats"); showView("stats"); loadDetailedStats();
  } else if (hash === "rhetoric") {
    switchView("rhetoric"); loadTags();
  }
}

/* ── Init ───────────────────────────────────────────────────────────── */
// ── UMAP pan/zoom (registered once; reads/writes umapTransform) ────────────
(function wireUmapPanZoom() {
  const svgEl = el.umapSvg;
  const UMAP_W = 900, UMAP_H = 560;
  svgEl.style.cursor = "grab";

  svgEl.addEventListener("wheel", e => {
    e.preventDefault();
    const rect = svgEl.getBoundingClientRect();
    const mx = (e.clientX - rect.left) / rect.width  * UMAP_W;
    const my = (e.clientY - rect.top)  / rect.height * UMAP_H;
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const newK = Math.max(0.5, Math.min(8, umapTransform.k * factor));
    umapTransform.tx = mx - (mx - umapTransform.tx) * (newK / umapTransform.k);
    umapTransform.ty = my - (my - umapTransform.ty) * (newK / umapTransform.k);
    umapTransform.k  = newK;
    applyUmapTransform();
  }, { passive: false });

  // Pan: use window listeners so drag survives leaving the SVG; no setPointerCapture,
  // which would redirect click to svgEl and prevent circle click handlers from firing.
  let drag = null;
  let didDrag = false;
  svgEl.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    drag = { startX: e.clientX, startY: e.clientY, tx0: umapTransform.tx, ty0: umapTransform.ty };
    didDrag = false;
    svgEl.style.cursor = "grabbing";
  });
  window.addEventListener("pointermove", e => {
    if (!drag) return;
    const dx = e.clientX - drag.startX, dy = e.clientY - drag.startY;
    if (!didDrag && Math.hypot(dx, dy) < 4) return;
    didDrag = true;
    const rect = svgEl.getBoundingClientRect();
    umapTransform.tx = drag.tx0 + dx * UMAP_W / rect.width;
    umapTransform.ty = drag.ty0 + dy * UMAP_H / rect.height;
    applyUmapTransform();
  });
  window.addEventListener("pointerup", () => {
    if (!drag) return;
    drag = null;
    svgEl.style.cursor = "grab";
  });
  // Suppress click that fires immediately after a drag-release
  svgEl.addEventListener("click", e => { if (didDrag) { e.stopPropagation(); } }, true);
  svgEl.addEventListener("dblclick", () => {
    umapTransform = { tx: 0, ty: 0, k: 1 };
    applyUmapTransform();
  });
}());

function init() {
  buildAlphaIndex();
  loadBrowsePage();
  loadClusters();
  loadStats();
  showView("welcome");
  applyTranslations();
  handleInitialHash();
}

init();
