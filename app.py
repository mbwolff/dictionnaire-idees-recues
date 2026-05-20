"""
Dictionnaire des idées reçues — Flask web application.

Routes
------
GET  /                      → main page
GET  /api/search?q=&lang=   → search existing entries
GET  /api/entry/<headword>  → single entry detail + neighbours
POST /api/generate          → validate noun + generate new entry (returns UMAP coords)
GET  /api/umap              → 2-D UMAP coordinates for corpus entries
GET  /api/clusters          → cluster summary for sidebar
GET  /api/suggest?lang=     → random underrepresented theme suggestion
"""

from flask import Flask, jsonify, request, render_template, abort
from pipeline import DictionairePipeline
import os, json, random
from pathlib import Path

app = Flask(__name__, template_folder=".", static_folder=".", static_url_path="/static")
app.config["JSON_AS_ASCII"] = False

pipeline = DictionairePipeline()


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/search")
def search():
    q    = request.args.get("q", "").strip()
    lang = request.args.get("lang", "fr")
    mode = request.args.get("mode", "text")
    limit = min(int(request.args.get("limit", 20)), 200)

    if mode == "cluster":
        cluster_id = int(request.args.get("cluster_id", -1))
        results = pipeline.cluster_search(cluster_id, limit, lang)
        return jsonify({"results": results, "total": len(results)})

    if not q:
        page  = int(request.args.get("page", 1))
        start = (page - 1) * limit
        results = pipeline.all_entries(start, limit, lang)
        return jsonify({"results": results, "total": pipeline.total_entries()})

    if mode == "semantic":
        results = pipeline.semantic_search(q, limit, lang)
    elif mode == "prefix":
        results = pipeline.prefix_search(q, limit, lang)
    else:
        results = pipeline.text_search(q, limit, lang)

    return jsonify({"results": results, "total": len(results)})


@app.route("/api/entry/<path:headword>")
def entry_detail(headword):
    lang = request.args.get("lang", "fr")
    data = pipeline.get_entry(headword.upper(), lang)
    if data is None:
        abort(404)
    return jsonify(data)


@app.route("/api/generate", methods=["POST"])
def generate():
    body   = request.get_json(force=True)
    word   = body.get("word", "").strip()
    lang   = body.get("lang", "fr")

    if not word:
        return jsonify({"error": "No word provided."}), 400
    if len(word) > 80:
        return jsonify({"error": "Input too long (max 80 characters)."}), 400

    result = pipeline.generate_entry(word, lang)
    return jsonify(result)




@app.route("/api/umap")
def umap():
    lang = request.args.get("lang", "fr")
    return jsonify(pipeline.umap_data(lang))


@app.route("/api/fuzzy")
def fuzzy():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    return jsonify(pipeline.fuzzy_suggest(q))


@app.route("/api/clusters")
def clusters():
    lang = request.args.get("lang", "fr")
    return jsonify(pipeline.cluster_summary(lang))


@app.route("/api/stats")
def stats():
    return jsonify(pipeline.stats())


@app.route("/api/random")
def random_entry():
    lang = request.args.get("lang", "fr")
    return jsonify(pipeline.random_entry(lang))


@app.route("/api/stats/detailed")
def stats_detailed():
    lang = request.args.get("lang", "fr")
    return jsonify(pipeline.detailed_stats(lang))


@app.route("/api/xrefs")
def xrefs():
    lang = request.args.get("lang", "fr")
    return jsonify(pipeline.xref_graph(lang))


_GAPS_FILE = Path(__file__).parent / "data" / "gap_candidates.json"
_gaps_cache: list | None = None

def _load_gaps() -> list:
    global _gaps_cache
    if _gaps_cache is None:
        _gaps_cache = json.loads(_GAPS_FILE.read_text("utf-8")) if _GAPS_FILE.exists() else []
    return _gaps_cache

from pipeline import CLUSTER_LABELS

@app.route("/api/suggest")
def suggest():
    lang = request.args.get("lang", "fr")
    gaps = _load_gaps()
    if not gaps:
        return jsonify({"error": "No gap data available."}), 404
    # Pick randomly from all gaps, weighted by gap_score
    scores  = [g["gap_score"] for g in gaps]
    total   = sum(scores)
    weights = [s / total for s in scores]
    pick    = random.choices(gaps, weights=weights, k=1)[0]
    cid     = pick["cluster_id"]
    labels  = CLUSTER_LABELS.get(lang, CLUSTER_LABELS["fr"])
    label   = labels[cid] if 0 <= cid < len(labels) else str(cid)
    members = [m[0] for m in pick["top_5_members"][:3]]
    return jsonify({"cluster_id": cid, "label": label, "members": members, "gap_score": pick["gap_score"]})


if __name__ == "__main__":
    # Port 5000 is hijacked by macOS AirPlay Receiver (Control Center) and
    # returns 403, so use 5050 instead.
    app.run(debug=True, port=5050)
