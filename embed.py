# Copyright (C) 2026  Mark Wolff <wolff.mark.b@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Step 2 — Embed every dictionary entry using a French sentence-transformer.

Produces:  embeddings.npz   (matrix + headword list)
"""

import json
import numpy as np
from pathlib import Path

ENTRIES_FILE = str(Path(__file__).parent / "data" / "dictionnaire_entries.json")
OUTPUT_FILE  = Path(__file__).parent / "data" / "embeddings.npz"

# ── Model selection ──────────────────────────────────────────────────────────
# CamemBERT fine-tuned for semantic similarity — best quality for French text
SENTENCE_MODEL = "dangvantuan/sentence-camembert-base"
FALLBACK_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


def load_entries(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def embed_with_sentence_transformers(texts: list[str], model_name: str) -> np.ndarray:
    """
    Use sentence-transformers library — returns one fixed-size vector per text.
    This is the recommended approach: mean-pooled, normalised embeddings.
    """
    from sentence_transformers import SentenceTransformer
    print(f"Loading sentence-transformer model: {model_name}")
    model = SentenceTransformer(model_name)
    print(f"Encoding {len(texts)} entries …")
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,   # cosine similarity == dot product
    )
    return embeddings  # shape: (N, hidden_size)


def embed_with_transformers(texts: list[str], model_name: str) -> np.ndarray:
    """
    Fallback: raw HuggingFace transformers with mean-pooling.
    Slower but works with any BERT-style model.
    """
    import torch
    from transformers import AutoTokenizer, AutoModel

    print(f"Loading tokenizer/model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    print(f"Using device: {device}")

    all_vecs = []
    batch_size = 16

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=128,
            return_tensors="pt",
        ).to(device)

        with torch.no_grad():
            output = model(**encoded)

        # Mean-pool over token dimension, masked for padding
        mask = encoded["attention_mask"].unsqueeze(-1).float()
        vecs = (output.last_hidden_state * mask).sum(1) / mask.sum(1)
        vecs = vecs.cpu().numpy()

        # L2-normalise
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        vecs = vecs / np.where(norms == 0, 1, norms)

        all_vecs.append(vecs)
        print(f"  Embedded {min(i + batch_size, len(texts))}/{len(texts)}")

    return np.vstack(all_vecs)


def build_texts(entries: list[dict]) -> list[str]:
    """
    Combine headword + entry text for richer embeddings.
    The headword itself carries meaning; prepending it helps.
    """
    return [f"{e['headword']}: {e['text']}" for e in entries]


def main():
    if not Path(ENTRIES_FILE).exists():
        raise FileNotFoundError(f"{ENTRIES_FILE} not found — run 01_parse.py first.")

    entries = load_entries(ENTRIES_FILE)
    texts   = build_texts(entries)
    headwords = [e["headword"] for e in entries]

    print(f"Loaded {len(entries)} entries.")

    try:
        embeddings = embed_with_sentence_transformers(texts, SENTENCE_MODEL)
        method = SENTENCE_MODEL
    except Exception as e1:
        print(f"sentence-camembert failed ({e1}), falling back to multilingual MiniLM …")
        embeddings = embed_with_sentence_transformers(texts, FALLBACK_MODEL)
        method = FALLBACK_MODEL

    print(f"\nEmbeddings shape: {embeddings.shape}  (method: {method})")

    np.savez(
        OUTPUT_FILE,
        embeddings=embeddings,
        headwords=np.array(headwords),
    )
    print(f"Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
