"""
Step 3 — Cluster entries, label clusters by rhetorical type,
build the cross-reference graph, and find semantic gaps.

Produces:
  clusters.json        — each entry annotated with cluster id
  gap_candidates.json  — candidate headwords for new entries
  reports/             — text reports + matplotlib plots
"""

import json
import numpy as np
from pathlib import Path
from collections import Counter, defaultdict

ENTRIES_FILE    = Path(__file__).parent / "data" / "dictionnaire_entries.json"
EMBEDDINGS_FILE = Path(__file__).parent / "data" / "embeddings.npz"
CLUSTERS_FILE   = Path(__file__).parent / "data" / "clusters.json"
GAPS_FILE       = Path(__file__).parent / "data" / "gap_candidates.json"
REPORTS_DIR     = Path(__file__).parent / "reports"

N_CLUSTERS = 12   # tunable — roughly one per major thematic zone


# ── Helpers ──────────────────────────────────────────────────────────────────

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def top_tags(entries_in_cluster: list[dict], n: int = 3) -> list[str]:
    counts = Counter(tag for e in entries_in_cluster for tag in e["tags"])
    return [t for t, _ in counts.most_common(n)]


# ── 1. Cluster ───────────────────────────────────────────────────────────────

def cluster_embeddings(embeddings: np.ndarray, n_clusters: int):
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import normalize

    X = normalize(embeddings)   # cosine via L2-normalised euclidean
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(X)
    return labels, km.cluster_centers_


# ── 2. Dimensionality reduction for plotting ─────────────────────────────────

def reduce_2d(embeddings: np.ndarray) -> np.ndarray:
    try:
        from sklearn.manifold import TSNE
        print("Running t-SNE …")
        return TSNE(n_components=2, random_state=42, perplexity=15).fit_transform(embeddings)
    except Exception:
        from sklearn.decomposition import PCA
        print("t-SNE unavailable, using PCA …")
        return PCA(n_components=2).fit_transform(embeddings)


# ── 3. Cross-reference graph ─────────────────────────────────────────────────

def build_xref_graph(entries: list[dict]) -> dict:
    """Returns adjacency list {headword: [referenced_headwords]}"""
    hw_set = {e["headword"].upper() for e in entries}
    graph = {}
    for e in entries:
        targets = []
        for xr in e["xrefs"]:
            # normalise and check it exists
            xr_norm = xr.upper().strip().rstrip(".")
            if xr_norm in hw_set:
                targets.append(xr_norm)
        if targets:
            graph[e["headword"].upper()] = targets
    return graph


# ── 4. Gap detection ─────────────────────────────────────────────────────────

def find_gaps(
    embeddings: np.ndarray,
    headwords: list[str],
    cluster_centers: np.ndarray,
    entries: list[dict],
) -> list[dict]:
    """
    For each cluster centroid, compute distance to the nearest actual entry.
    Centroids that are 'far' from any entry = semantic gaps.
    Also look for midpoints between high-density pairs with nothing between them.
    """
    from sklearn.preprocessing import normalize

    X = normalize(embeddings)
    centers = normalize(cluster_centers)

    gaps = []

    for ci, center in enumerate(centers):
        sims = X @ center          # cosine similarities
        nearest_idx = int(np.argmax(sims))
        nearest_sim = float(sims[nearest_idx])
        nearest_hw  = headwords[nearest_idx]

        # Cluster members
        member_sims = sorted(
            [(headwords[i], float(sims[i])) for i in range(len(headwords))],
            key=lambda x: -x[1],
        )[:5]

        gaps.append(
            {
                "cluster_id": ci,
                "nearest_headword": nearest_hw,
                "nearest_similarity": round(nearest_sim, 4),
                "top_5_members": member_sims,
                "gap_score": round(1.0 - nearest_sim, 4),  # higher = bigger gap
            }
        )

    # Sort by gap score descending
    gaps.sort(key=lambda x: -x["gap_score"])
    return gaps


# ── 5. Plot ──────────────────────────────────────────────────────────────────

def plot_clusters(coords_2d, labels, headwords, output_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm

        fig, ax = plt.subplots(figsize=(14, 10))
        colors = cm.tab20(np.linspace(0, 1, max(labels) + 1))

        for label in sorted(set(labels)):
            mask = labels == label
            ax.scatter(
                coords_2d[mask, 0],
                coords_2d[mask, 1],
                c=[colors[label]],
                label=f"Cluster {label}",
                alpha=0.7,
                s=60,
            )

        # Annotate a sample of headwords
        rng = np.random.default_rng(0)
        sample = rng.choice(len(headwords), size=min(40, len(headwords)), replace=False)
        for i in sample:
            ax.annotate(
                headwords[i],
                (coords_2d[i, 0], coords_2d[i, 1]),
                fontsize=6,
                alpha=0.8,
            )

        ax.set_title("Dictionnaire des idées reçues — semantic clusters", fontsize=13)
        ax.legend(loc="upper right", fontsize=7, ncol=2)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150)
        plt.close()
        print(f"  Plot saved → {output_path}")
    except ImportError:
        print("  matplotlib not available — skipping plot.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    REPORTS_DIR.mkdir(exist_ok=True)

    entries_data  = json.loads(Path(ENTRIES_FILE).read_text(encoding="utf-8"))
    npz           = np.load(EMBEDDINGS_FILE, allow_pickle=True)
    embeddings    = npz["embeddings"]
    headwords     = list(npz["headwords"])

    print(f"Clustering {len(headwords)} entries into {N_CLUSTERS} clusters …")
    labels, centers = cluster_embeddings(embeddings, N_CLUSTERS)

    # Annotate entries with cluster id
    hw_to_cluster = {hw: int(labels[i]) for i, hw in enumerate(headwords)}
    for e in entries_data:
        e["cluster_id"] = hw_to_cluster.get(e["headword"], -1)

    # Group by cluster for reporting
    clusters = defaultdict(list)
    for e in entries_data:
        clusters[e["cluster_id"]].append(e)

    print("\n── Cluster summary ──")
    cluster_report_lines = []
    for cid in sorted(clusters):
        members  = clusters[cid]
        tags     = top_tags(members)
        names    = [e["headword"] for e in members]
        line = f"Cluster {cid:2d} ({len(members):3d} entries)  tags={tags}"
        print(f"  {line}")
        print(f"    {', '.join(names[:8])}{'…' if len(names) > 8 else ''}")
        cluster_report_lines.append(line + "\n    " + ", ".join(names[:8]))

    (REPORTS_DIR / "cluster_summary.txt").write_text(
        "\n\n".join(cluster_report_lines), encoding="utf-8"
    )

    # Cross-reference graph
    xref_graph = build_xref_graph(entries_data)
    print(f"\nCross-reference graph: {len(xref_graph)} nodes with outgoing refs")
    xref_report = "\n".join(
        f"{src} → {', '.join(tgts)}" for src, tgts in sorted(xref_graph.items())
    )
    (REPORTS_DIR / "xref_graph.txt").write_text(xref_report, encoding="utf-8")

    # Save annotated entries
    Path(CLUSTERS_FILE).write_text(
        json.dumps(entries_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSaved annotated entries → {CLUSTERS_FILE}")

    # Gap detection
    gaps = find_gaps(embeddings, headwords, centers, entries_data)
    Path(GAPS_FILE).write_text(
        json.dumps(gaps, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved gap candidates → {GAPS_FILE}")

    print("\n── Top 5 semantic gaps ──")
    for g in gaps[:5]:
        print(f"  Cluster {g['cluster_id']:2d}  gap_score={g['gap_score']:.3f}")
        print(f"    Nearest entry: {g['nearest_headword']}")
        print(f"    Neighbours: {[h for h, _ in g['top_5_members']]}")

    # 2-D projection + plot
    coords = reduce_2d(embeddings)
    plot_clusters(coords, labels, headwords, REPORTS_DIR / "clusters.png")


if __name__ == "__main__":
    main()
