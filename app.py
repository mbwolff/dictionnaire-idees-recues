"""
Dictionnaire des idées reçues — Flask web application.

Routes
------
GET  /                      → main page
GET  /api/search?q=&lang=   → search existing entries
GET  /api/entry/<headword>  → single entry detail + neighbours
POST /api/generate          → validate noun + generate new entry
GET  /api/generated         → last 10 generated entries (most recent first)
GET  /api/tsne              → 2-D t-SNE coordinates for all entries
GET  /api/clusters          → cluster summary for sidebar
"""

from flask import Flask, jsonify, request, render_template, abort
from pipeline import DictionairePipeline
import os

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

    if mode == "tag":
        tag = request.args.get("tag", "")
        results = pipeline.tag_search(tag, limit, lang)
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


@app.route("/api/generated")
def generated():
    lang  = request.args.get("lang", "fr")
    limit = min(int(request.args.get("limit", 10)), 50)
    return jsonify(pipeline.recent_generated(limit, lang))


@app.route("/api/tags")
def tags():
    lang = request.args.get("lang", "fr")
    return jsonify(pipeline.tag_summary(lang))


@app.route("/api/tsne")
def tsne():
    lang = request.args.get("lang", "fr")
    return jsonify(pipeline.tsne_data(lang))


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


if __name__ == "__main__":
    # Port 5000 is hijacked by macOS AirPlay Receiver (Control Center) and
    # returns 403, so use 5050 instead.
    app.run(debug=True, port=5050)
