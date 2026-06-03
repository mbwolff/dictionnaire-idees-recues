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
pipeline.py — core ML/NLP pipeline for the Flask app.

Entry generation backend is chosen by the GENERATOR env var:
  GENERATOR=ollama        (default) — local Ollama, completely free
  GENERATOR=transformers  — local HuggingFace transformers, completely free
  GENERATOR=claude        — Anthropic API, requires ANTHROPIC_API_KEY

Model overrides:
  OLLAMA_MODEL  (default: mistral)
  OLLAMA_HOST   (default: http://localhost:11434)
  HF_MODEL      (default: mistralai/Mistral-7B-Instruct-v0.3)
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
ENTRIES_FILE    = BASE_DIR / "data" / "clusters.json"
EMBEDDINGS_FILE = BASE_DIR / "data" / "embeddings.npz"
UMAP_FILE       = BASE_DIR / "data" / "umap_coords.npy"

# ── Generator config ──────────────────────────────────────────────────────────
GENERATOR_BACKEND = os.environ.get("GENERATOR", "ollama").lower()
OLLAMA_HOST       = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL      = os.environ.get("OLLAMA_MODEL", "mistral")
HF_MODEL          = os.environ.get("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")
# ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# CLAUDE_MODEL      = "claude-sonnet-4-20250514"

# ── Cluster labels ────────────────────────────────────────────────────────────
CLUSTER_LABELS = {
    "fr": [
        "Types sociaux & religion", "Nations, arts & professions", "Stéréotypes & corps de métiers",
        "Vie quotidienne & passions", "Institutions & polémiques", "Arts & vie bourgeoise",
        "Gastronomie & intérieur", "Arts, lettres & savoirs", "Exotisme, corps & mœurs",
        "Vices, politique & société", "Guerre, force & science", "Antiquité, culture & spectacle",
    ],
    "en": [
        "Social Types & Religion", "Nations, Arts & Professions", "Stereotypes & Trades",
        "Daily Life & Passions", "Institutions & Polemics", "Arts & Bourgeois Life",
        "Gastronomy & Interiors", "Arts, Letters & Knowledge", "Exoticism, Body & Manners",
        "Vices, Politics & Society", "War, Force & Science", "Antiquity, Culture & Spectacle",
    ],
}


RHETORICAL_TAG_LABELS = {
    "fr": {
        "verite_generale":        "Vérité générale",
        "nominal_assertion":      "Assertion nominale",
        "prescriptive_imperative":"Impératif prescriptif",
        "circular_definition":    "Définition circulaire",
        "social_performance":     "Performance sociale",
        "superlative_assertion":  "Assertion superlative",
        "danger_assertion":       "Assertion de danger",
        "self_undermining":       "Auto-contradiction",
        "mythification":          "Mythification",
        "cross_reference":        "Renvoi",
    },
    "en": {
        "verite_generale":        "General truth",
        "nominal_assertion":      "Nominal assertion",
        "prescriptive_imperative":"Prescriptive imperative",
        "circular_definition":    "Circular definition",
        "social_performance":     "Social performance",
        "superlative_assertion":  "Superlative assertion",
        "danger_assertion":       "Danger assertion",
        "self_undermining":       "Self-undermining",
        "mythification":          "Mythification",
        "cross_reference":        "Cross-reference",
    },
}

# ── Shared prompt components ──────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Tu es Gustave Flaubert rédigeant le Dictionnaire des idées reçues. "
    "Génère UNIQUEMENT une entrée de dictionnaire satirique. "
    "Format : une ou deux phrases courtes, ironiques, formulaiques — "
    "ce qu'un bourgeois satisfait dirait en société. "
    "Commence directement par la définition, sans répéter le mot, "
    "sans introduction, sans explication."
)

FEW_SHOT = (
    "Exemples authentiques :\n"
    "  ABSINTHE. Poison extra-violent. Un verre et vous êtes mort.\n"
    "  BUDGET. N'est jamais en équilibre.\n"
    "  HOMÈRE. N'a jamais existé. Célèbre par ses éclats de rire.\n"
    "  PROGRÈS. Cause de la dégénérescence de la race.\n"
    "  MARIAGE. Est le tombeau de l'amour."
)


def build_user_prompt(
    headword: str,
    neighbours: list[dict],
    examples: list[dict] | None = None,
) -> str:
    if examples:
        import random as _rnd
        sample = _rnd.sample(examples, min(5, len(examples)))
        few_shot = "Exemples authentiques :\n" + "\n".join(
            f"  {e['headword'].upper()}. {e['text']}" for e in sample
        )
    else:
        few_shot = FEW_SHOT
    neighbour_block = "\n".join(
        f"  {n['headword'].upper()}. {n['text']}" for n in neighbours[:5]
    )
    return (
        f"{few_shot}\n\n"
        f"Entrées voisines :\n{neighbour_block}\n\n"
        f"Nouvelle entrée pour : {headword.upper()}"
    )


def clean_output(text: str) -> str:
    """Strip accidental headword echo, markdown, excess whitespace."""
    text = re.sub(r"^[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜ\s\-]{2,30}[.:\-]\s*", "", text)
    text = re.sub(r"\*+", "", text)
    text = re.sub(r'"([^"]*)"', r"« \1 »", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Trim to last complete sentence if text ends mid-sentence
    if text and text[-1] not in ".!?»\"":
        match = re.search(r"^(.*[.!?»\"])\s+\S", text)
        if match:
            text = match.group(1)
    return text


# ═════════════════════════════════════════════════════════════════════════════
# Generator backends
# ═════════════════════════════════════════════════════════════════════════════

class BaseGenerator(ABC):
    @abstractmethod
    def generate(self, headword: str, neighbours: list[dict], examples: list[dict] | None = None) -> str: ...

    def name(self) -> str:
        return self.__class__.__name__


class OllamaGenerator(BaseGenerator):
    """
    Local Ollama — completely free, no API key required.

    Setup:
      1. Install Ollama from https://ollama.com
      2. Pull a model:  ollama pull mistral
      3. Ollama starts automatically (or run: ollama serve)

    Good models for French satirical text:
      mistral        7B, ~4 GB,  best French quality, recommended
      gemma3:4b      4B, ~2.5 GB, fast, decent French
      llama3.2:3b    3B, ~2 GB,  fastest, lightest

    Override with env vars:
      OLLAMA_MODEL=gemma3:4b
      OLLAMA_HOST=http://localhost:11434
    """

    def __init__(self):
        self.host  = OLLAMA_HOST.rstrip("/")
        self.model = OLLAMA_MODEL
        self._check()

    def _check(self):
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=3) as r:
                data = json.loads(r.read())
            available = [m["name"].split(":")[0] for m in data.get("models", [])]
            base = self.model.split(":")[0]
            if base not in available:
                print(
                    f"[Ollama] WARNING: '{self.model}' not pulled yet.\n"
                    f"  Run: ollama pull {self.model}\n"
                    f"  Available: {available or '(none)'}"
                )
            else:
                print(f"[Ollama] Ready — {self.model}")
        except Exception as exc:
            print(
                f"[Ollama] Cannot reach {self.host}: {exc}\n"
                f"  Make sure Ollama is running: ollama serve"
            )

    def generate(self, headword: str, neighbours: list[dict], examples: list[dict] | None = None) -> str:
        payload = json.dumps({
            "model":  self.model,
            "stream": False,
            "options": {
                "temperature":    0.85,
                "top_p":          0.92,
                "repeat_penalty": 1.15,
                "num_predict":    200,
            },
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": build_user_prompt(headword, neighbours, examples)},
            ],
        }).encode()

        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())

        return clean_output(data.get("message", {}).get("content", ""))


class TransformersGenerator(BaseGenerator):
    """
    HuggingFace transformers running locally — completely free after download.
    Model weights are downloaded once (~4-14 GB depending on model).

    Requirements:
      pip install transformers torch accelerate

    Lighter options (set HF_MODEL env var):
      microsoft/Phi-3-mini-4k-instruct   ~2.3 GB, good French
      google/gemma-2-2b-it               ~5 GB
      mistralai/Mistral-7B-Instruct-v0.3 ~14 GB (default)
    """

    def __init__(self):
        self.model_id  = HF_MODEL
        self._pipeline = None  # lazy-loaded on first call

    def _load(self):
        if self._pipeline is not None:
            return
        print(f"[Transformers] Loading {self.model_id} — first call may take a few minutes…")
        import torch
        from transformers import pipeline as hf_pipeline

        device = 0 if torch.cuda.is_available() else -1
        self._pipeline = hf_pipeline(
            "text-generation",
            model=self.model_id,
            device=device,
            torch_dtype="auto" if torch.cuda.is_available() else None,
            trust_remote_code=True,
        )
        print(f"[Transformers] Ready on device {device}.")

    def generate(self, headword: str, neighbours: list[dict], examples: list[dict] | None = None) -> str:
        self._load()
        # Mistral-style instruction format; works for most instruct-tuned models
        prompt = (
            f"<s>[INST] {SYSTEM_PROMPT}\n\n"
            f"{build_user_prompt(headword, neighbours, examples)} [/INST]"
        )
        outputs = self._pipeline(
            prompt,
            max_new_tokens=200,
            do_sample=True,
            temperature=0.85,
            top_p=0.92,
            repetition_penalty=1.15,
            return_full_text=False,
        )
        return clean_output(outputs[0]["generated_text"])


class ClaudeGenerator(BaseGenerator):
    """
    Anthropic Claude API — highest quality but costs per request.
    Requires ANTHROPIC_API_KEY environment variable.
    """

    def __init__(self):
        if not ANTHROPIC_API_KEY:
            print("[Claude] WARNING: ANTHROPIC_API_KEY not set.")

    def generate(self, headword: str, neighbours: list[dict], examples: list[dict] | None = None) -> str:
        if not ANTHROPIC_API_KEY:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

        payload = json.dumps({
            "model":      CLAUDE_MODEL,
            "max_tokens": 200,
            "system":     SYSTEM_PROMPT,
            "messages":   [{"role": "user", "content": build_user_prompt(headword, neighbours, examples)}],
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())

        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"].strip()
        return ""


def make_generator() -> BaseGenerator:
    if GENERATOR_BACKEND == "transformers":
        print(f"[Generator] Backend: HuggingFace Transformers ({HF_MODEL})")
        return TransformersGenerator()
    if GENERATOR_BACKEND == "claude":
        print(f"[Generator] Backend: Claude ({CLAUDE_MODEL})")
        return ClaudeGenerator()
    print(f"[Generator] Backend: Ollama ({OLLAMA_MODEL} @ {OLLAMA_HOST})")
    return OllamaGenerator()


# ═════════════════════════════════════════════════════════════════════════════
# Translation
# ═════════════════════════════════════════════════════════════════════════════

class Translator:
    def __init__(self):
        self._cache: dict[str, str] = {}
        self._available = False
        try:
            from deep_translator import GoogleTranslator
            self._gt = GoogleTranslator
            self._available = True
        except ImportError:
            print("[Translator] deep-translator not installed; translations disabled.")

    def translate(self, text: str, src: str = "fr", dest: str = "en") -> str:
        if not self._available or src == dest or not text.strip():
            return text
        key = f"{src}:{dest}:{text[:120]}"
        if key in self._cache:
            return self._cache[key]
        try:
            result = self._gt(source=src, target=dest).translate(text)
            self._cache[key] = result or text
        except Exception as exc:
            print(f"[Translator] {exc}")
            self._cache[key] = text
        return self._cache[key]

    def to_english(self, text: str) -> str:
        return self.translate(text, "fr", "en")

    def to_french(self, text: str) -> str:
        return self.translate(text, "en", "fr")


# ═════════════════════════════════════════════════════════════════════════════
# Noun validation
# ═════════════════════════════════════════════════════════════════════════════

class NounValidator:
    def __init__(self):
        self._nlp = None
        try:
            import spacy
            self._nlp = spacy.load("fr_core_news_sm")
            print("[NounValidator] spaCy fr_core_news_sm loaded.")
        except Exception as exc:
            print(f"[NounValidator] spaCy unavailable ({exc}); heuristic fallback active.")

    # French vowels incl. accented forms
    _VOWEL_RE = re.compile(r"[aeiouyàâæéèêëîïôœùûü]", re.IGNORECASE)

    def validate(self, word: str) -> dict:
        word = word.strip()
        if not word:
            return {"valid": False, "pos": "", "lemma": word, "reason": "Empty input."}
        return {"valid": True, "pos": "", "lemma": word.upper(), "reason": ""}

    def _wiktionary_exists(self, word: str) -> bool:
        """Return True if word has a French Wiktionary page (fail-open on network error)."""
        import requests as _req
        url = (
            "https://fr.wiktionary.org/w/api.php?action=query"
            f"&titles={urllib.parse.quote(word.lower().strip())}"
            "&format=json&redirects=1"
        )
        try:
            r = _req.get(url, timeout=5, headers={"User-Agent": "DictionnaireApp/1.0"})
            pages = r.json().get("query", {}).get("pages", {})
            return "-1" not in pages
        except Exception:
            return True  # network error → fail open

    def _validate_spacy(self, word: str) -> dict:
        doc   = self._nlp(word)
        token = doc[0]
        pos   = token.pos_
        lemma = token.lemma_.upper()
        if pos in ("NOUN", "PROPN"):
            # For single words, verify the word actually exists in French
            if " " not in word.strip():
                known = self._wiktionary_exists(word)
                if not known and lemma.lower() != word.lower():
                    known = self._wiktionary_exists(lemma)
                if not known:
                    return {"valid": False, "pos": pos, "lemma": lemma,
                            "reason": f"'{word}' is not a recognized French word."}
            return {"valid": True, "pos": pos, "lemma": lemma, "reason": ""}
        if len(doc) > 1 and any(t.pos_ in ("NOUN", "PROPN") for t in doc):
            return {"valid": True, "pos": "NOUN", "lemma": word.upper(), "reason": ""}
        labels = {"VERB": "verb", "ADJ": "adjective", "ADV": "adverb",
                  "ADP": "preposition", "DET": "determiner"}
        return {
            "valid": False, "pos": pos, "lemma": lemma,
            "reason": f"'{word}' appears to be a {labels.get(pos, pos.lower())}, not a noun.",
        }

    def _validate_heuristic(self, word: str) -> dict:
        w = word.lower().strip()
        if len(w) < 2:
            return {"valid": False, "pos": "", "lemma": word.upper(), "reason": "Too short."}
        if re.match(r".+(er|ir|re)$", w) and len(w) > 4:
            return {"valid": False, "pos": "VERB", "lemma": word.upper(),
                    "reason": "Looks like a French verb infinitive."}
        if w in {"très", "bien", "mal", "peu", "trop", "aussi", "même"}:
            return {"valid": False, "pos": "ADV", "lemma": word.upper(),
                    "reason": "This is an adverb."}
        return {"valid": True, "pos": "NOUN", "lemma": word.upper(), "reason": ""}


# ═════════════════════════════════════════════════════════════════════════════
# Main pipeline
# ═════════════════════════════════════════════════════════════════════════════

class DictionairePipeline:

    def __init__(self):
        self.translator = Translator()
        self.validator  = NounValidator()
        self.generator  = make_generator()
        self._entries: list[dict]      = []
        self._embeddings: Optional[np.ndarray] = None
        self._headwords: list[str]     = []
        self._hw_index: dict[str, int] = {}
        self._sentence_model           = None
        self._umap_cache: Optional[np.ndarray] = None
        self._load_data()

    def _load_data(self):
        if ENTRIES_FILE.exists():
            self._entries = json.loads(ENTRIES_FILE.read_text("utf-8"))
            self._entry_index: dict[str, int] = {
                e["headword"].upper(): i for i, e in enumerate(self._entries)
            }
            print(f"[Pipeline] {len(self._entries)} Flaubert entries loaded.")
        else:
            print(f"[Pipeline] WARNING: {ENTRIES_FILE} not found. Run 01_parse.py first.")
            self._entry_index = {}

        if EMBEDDINGS_FILE.exists():
            npz = np.load(EMBEDDINGS_FILE, allow_pickle=True)
            self._embeddings = npz["embeddings"].astype(np.float32)
            self._headwords  = [h.upper() for h in npz["headwords"]]
            self._hw_index   = {hw: i for i, hw in enumerate(self._headwords)}
            print(f"[Pipeline] Embeddings: {self._embeddings.shape}")
        else:
            print("[Pipeline] No embeddings — semantic search will fall back to text search.")

        if UMAP_FILE.exists():
            self._umap_cache = np.load(UMAP_FILE).astype(np.float32)
            print(f"[Pipeline] UMAP coords loaded: {self._umap_cache.shape}")

    def _format_entry(self, entry: dict, lang: str) -> dict:
        text = entry.get("text", "")
        hw   = entry.get("headword", "")
        cid  = entry.get("cluster_id")
        if not isinstance(cid, int):
            cid = -1
        scores = entry.get("membership_scores", [])
        # Secondary cluster: highest-scoring cluster that isn't the primary
        if len(scores) == len(CLUSTER_LABELS["fr"]) and cid >= 0:
            pri_score = scores[cid]
            sec_cid = int(max(
                (i for i in range(len(scores)) if i != cid),
                key=lambda i: scores[i],
            ))
            sec_score = scores[sec_cid]
            # Compound criterion: primary meaningfully above baseline AND
            # secondary nearly as strong (sec/pri >= 0.90)
            show_secondary = (
                pri_score >= 0.10 and
                sec_score / pri_score >= 0.90
            )
        else:
            pri_score, sec_cid, sec_score, show_secondary = 0.0, -1, 0.0, False
        result = {
            "headword":               hw,
            "text":                   text,
            "tags":                   entry.get("tags", []),
            "xrefs":                  entry.get("xrefs", []),
            "cluster_id":             cid,
            "cluster_label":          (
                CLUSTER_LABELS[lang][cid]
                if 0 <= cid < len(CLUSTER_LABELS["fr"]) else ""
            ),
            "primary_cluster_score":  round(pri_score, 4),
            "secondary_cluster_id":   sec_cid,
            "secondary_cluster_label":(
                CLUSTER_LABELS[lang][sec_cid]
                if 0 <= sec_cid < len(CLUSTER_LABELS["fr"]) else ""
            ),
            "secondary_cluster_score": round(sec_score, 4),
            "show_secondary_cluster": show_secondary,
            "membership_scores":      scores,
            "is_generated":  entry.get("is_generated", False),
            "generator":     entry.get("generator", ""),
            "lang":          lang,
        }
        if lang == "en":
            tr = entry.get("text_en") or self.translator.to_english(text)
            tr = re.sub(r'«\s*', '“', tr)   # « → "
            tr = re.sub(r'\s*»', '”', tr)   # » → "
            result["text_translated"] = tr
            result["headword_translated"] = entry.get("headword_en") or self.translator.to_english(hw)
            result["tag_labels"] = [RHETORICAL_TAG_LABELS["en"].get(t, t) for t in entry.get("tags", [])]
        else:
            result["text_translated"]     = text
            result["headword_translated"] = hw
            result["tag_labels"] = [RHETORICAL_TAG_LABELS["fr"].get(t, t) for t in entry.get("tags", [])]
        return result

    def total_entries(self) -> int:
        return len(self._entries)

    def stats(self) -> dict:
        return {
            "flaubert_entries":  len(self._entries),
            "embeddings_loaded": self._embeddings is not None,
            "clusters":          len(CLUSTER_LABELS["fr"]),
            "generator":         self.generator.name(),
        }

    def umap_data(self, lang: str) -> list[dict]:
        if self._embeddings is None:
            return []
        if self._umap_cache is None:
            if UMAP_FILE.exists():
                print("[Pipeline] Loading UMAP from disk…")
                self._umap_cache = np.load(UMAP_FILE).astype(np.float32)
            else:
                from sklearn.preprocessing import normalize
                import umap
                print("[Pipeline] Computing UMAP…")
                coords = umap.UMAP(
                    n_components=2, random_state=42, n_neighbors=15, min_dist=0.1,
                ).fit_transform(normalize(self._embeddings))
                self._umap_cache = coords.astype(np.float32)
                np.save(UMAP_FILE, self._umap_cache)
                print("[Pipeline] UMAP done.")
        coords = self._umap_cache
        labels = CLUSTER_LABELS[lang]
        result = []
        for i, e in enumerate(self._entries):
            if i >= len(coords):
                break
            cid = e.get("cluster_id")
            if not isinstance(cid, int):
                cid = -1
            hw     = e["headword"]
            scores = e.get("membership_scores", [])
            pri_score = float(scores[cid]) if (0 <= cid < len(scores)) else 0.0
            sec_cid_e = -1
            show_sec  = False
            if len(scores) == len(CLUSTER_LABELS["fr"]) and cid >= 0:
                sec_cid_e = int(max(
                    (j for j in range(len(scores)) if j != cid),
                    key=lambda j: scores[j],
                ))
                sec_score_e = float(scores[sec_cid_e])
                show_sec = pri_score >= 0.10 and (sec_score_e / pri_score >= 0.90 if pri_score > 0 else False)
            text = e.get("text", "")
            snippet = text[:70].rsplit(" ", 1)[0] + "…" if len(text) > 70 else text
            result.append({
                "headword":              hw,
                "headword_display":      e.get("headword_en", hw) if lang == "en" else hw,
                "x":                     float(coords[i][0]),
                "y":                     float(coords[i][1]),
                "cluster_id":            cid,
                "cluster_label":         labels[cid] if 0 <= cid < len(labels) else "",
                "primary_cluster_score": round(pri_score, 4),
                "secondary_cluster_id":  sec_cid_e,
                "show_secondary_cluster": show_sec,
                "text_snippet":          snippet,
            })
        return result

    def fuzzy_suggest(self, query: str, n: int = 5) -> list[str]:
        import difflib
        all_hw = [e["headword"] for e in self._entries]
        return difflib.get_close_matches(query.upper(), all_hw, n=n, cutoff=0.6)

    def random_entry(self, lang: str) -> dict:
        import random as _rnd
        e   = _rnd.choice(self._entries)
        fe  = self._format_entry(e, lang)
        hw  = e["headword"].upper()
        fe["neighbours"] = self._get_neighbours(hw, lang)
        idx = self._entry_index.get(hw, -1)
        fe["prev_headword"] = self._entries[idx - 1]["headword"] if idx > 0 else None
        fe["next_headword"] = self._entries[idx + 1]["headword"] if idx < len(self._entries) - 1 else None
        if self._umap_cache is not None and 0 <= idx < len(self._umap_cache):
            fe["umap_x"] = float(self._umap_cache[idx][0])
            fe["umap_y"] = float(self._umap_cache[idx][1])
        return fe

    def detailed_stats(self, lang: str) -> dict:
        from collections import Counter
        entries = self._entries
        tag_counts = Counter(tag for e in entries for tag in e.get("tags", []))
        tag_labels_map = RHETORICAL_TAG_LABELS[lang]
        tags = [{"tag": t, "label": tag_labels_map.get(t, t), "count": c}
                for t, c in sorted(tag_counts.items(), key=lambda x: -x[1])]
        cluster_counts = Counter(
            e.get("cluster_id") for e in entries
            if isinstance(e.get("cluster_id"), int) and e.get("cluster_id", -1) >= 0
        )
        cls_labels = CLUSTER_LABELS[lang]
        clusters = [{"cluster_id": cid, "label": cls_labels[cid] if cid < len(cls_labels) else str(cid), "count": cnt}
                    for cid, cnt in sorted(cluster_counts.items())]
        lengths = sorted(len(e.get("text", "")) for e in entries)
        avg_len = round(sum(lengths) / len(lengths)) if lengths else 0
        k = len(CLUSTER_LABELS["fr"])
        dual = sum(
            1 for e in entries
            if isinstance(e.get("cluster_id"), int) and e.get("cluster_id", -1) >= 0
            and len(e.get("membership_scores", [])) == k
            and e["membership_scores"][e["cluster_id"]] >= 0.10
            and max((e["membership_scores"][j] for j in range(k) if j != e["cluster_id"]), default=0)
               / e["membership_scores"][e["cluster_id"]] >= 0.90
        )
        return {
            "flaubert_entries":  len(entries),
            "generated_entries": 0,
            "dual_theme":        dual,
            "tags":              tags,
            "clusters":          clusters,
            "text_length":       {
                "avg":    avg_len,
                "median": lengths[len(lengths) // 2] if lengths else 0,
                "min":    min(lengths, default=0),
                "max":    max(lengths, default=0),
            },
            "xrefs": {
                "entries_with_xrefs": sum(1 for e in entries if e.get("xrefs")),
                "total_edges":        sum(len(e.get("xrefs", [])) for e in entries),
            },
        }

    def xref_graph(self, lang: str) -> dict:
        hw_map = {e["headword"].upper(): e for e in self._entries}
        nodes: dict[str, dict] = {}
        edges = []
        for e in self._entries:
            if not e.get("xrefs"):
                continue
            src = e["headword"]
            if src not in nodes:
                nodes[src] = {
                    "id":         src,
                    "display":    e.get("headword_en", src) if lang == "en" else src,
                    "cluster_id": e.get("cluster_id", -1) if isinstance(e.get("cluster_id"), int) else -1,
                }
            for xr in e["xrefs"]:
                tgt = xr.upper().strip().rstrip(".")
                if tgt in hw_map:
                    if tgt not in nodes:
                        te = hw_map[tgt]
                        nodes[tgt] = {
                            "id":         tgt,
                            "display":    te.get("headword_en", tgt) if lang == "en" else tgt,
                            "cluster_id": te.get("cluster_id", -1) if isinstance(te.get("cluster_id"), int) else -1,
                        }
                    edges.append({"source": src, "target": tgt})
        return {"nodes": list(nodes.values()), "edges": edges}

    def tag_summary(self, lang: str) -> list[dict]:
        from collections import Counter
        counts: Counter = Counter(
            tag for e in self._entries for tag in e.get("tags", [])
        )
        labels = RHETORICAL_TAG_LABELS[lang]
        return [
            {"tag": tag, "label": labels.get(tag, tag), "count": count}
            for tag, count in sorted(counts.items(), key=lambda x: -x[1])
        ]

    def tag_search(self, tag: str, limit: int, lang: str) -> list[dict]:
        results = [
            self._format_entry(e, lang)
            for e in self._entries
            if tag in e.get("tags", [])
        ]
        results.sort(key=lambda x: x["headword"])
        return results[:limit]

    def all_entries(self, start: int, limit: int, lang: str) -> list[dict]:
        return [self._format_entry(e, lang) for e in self._entries[start:start + limit]]

    def cluster_search(self, cluster_id: int, limit: int, lang: str) -> list[dict]:
        results = [self._format_entry(e, lang) for e in self._entries if e.get("cluster_id") == cluster_id]
        results.sort(key=lambda x: x["headword"])
        return results[:limit]

    def prefix_search(self, prefix: str, limit: int, lang: str) -> list[dict]:
        import unicodedata
        def _strip(s: str) -> str:
            return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
        p = _strip(prefix.upper())
        results = [
            self._format_entry(e, lang) for e in self._entries
            if _strip(e.get("headword", "").upper()).startswith(p)
        ]
        results.sort(key=lambda x: x["headword"])
        return results[:limit]

    def text_search(self, query: str, limit: int, lang: str) -> list[dict]:
        import unicodedata
        def _strip(s: str) -> str:
            return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
        q = _strip(query.upper())
        results = [
            self._format_entry(e, lang)
            for e in self._entries
            if q in _strip(e.get("headword", "").upper()) or q in _strip(e.get("text", "").upper())
        ]
        return results[:limit]

    def semantic_search(self, query: str, limit: int, lang: str) -> list[dict]:
        if self._embeddings is None:
            return self.text_search(query, limit, lang)
        fr_query = self.translator.to_french(query) if lang == "en" else query
        vec = self._approximate_vector(fr_query)
        if vec is None:
            return self.text_search(query, limit, lang)
        sims = self._embeddings @ vec
        top  = np.argsort(sims)[::-1][:limit]
        hw_map = {e["headword"].upper(): e for e in self._entries}
        results = []
        for i in top:
            entry = hw_map.get(self._headwords[i])
            if entry:
                fe = self._format_entry(entry, lang)
                fe["similarity"] = round(float(sims[i]), 4)
                results.append(fe)
        return results

    def _get_sentence_model(self):
        if self._sentence_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._sentence_model = SentenceTransformer("dangvantuan/sentence-camembert-base")
                print("[Pipeline] Sentence model loaded.")
            except Exception as exc:
                print(f"[Pipeline] Could not load sentence model: {exc}")
        return self._sentence_model

    def _approximate_vector(self, text: str) -> Optional[np.ndarray]:
        words = [w.upper().strip(".,;:!?") for w in text.split()]
        idxs  = [self._hw_index[w] for w in words if w in self._hw_index]
        if not idxs:
            for hw, idx in self._hw_index.items():
                if any(w in hw or hw in w for w in words):
                    idxs.append(idx); break
        if idxs:
            vec = self._embeddings[idxs].mean(axis=0)
            n = np.linalg.norm(vec)
            return vec / (n + 1e-9)
        # No headword match — encode with the sentence model (same space as stored embeddings)
        model = self._get_sentence_model()
        if model is not None:
            vec = model.encode(text, normalize_embeddings=True).astype(np.float32)
            return vec
        # Last resort: global mean (not useful but won't crash)
        vec = self._embeddings.mean(axis=0)
        n = np.linalg.norm(vec)
        return vec / (n + 1e-9)

    def get_entry(self, headword: str, lang: str) -> Optional[dict]:
        hw = headword.upper()
        for e in self._entries:
            if e.get("headword", "").upper() == hw:
                fe = self._format_entry(e, lang)
                fe["neighbours"] = self._get_neighbours(hw, lang)
                idx = self._entry_index.get(hw, -1)
                fe["prev_headword"] = self._entries[idx - 1]["headword"] if idx > 0 else None
                fe["next_headword"] = self._entries[idx + 1]["headword"] if idx < len(self._entries) - 1 else None
                if self._umap_cache is not None and 0 <= idx < len(self._umap_cache):
                    fe["umap_x"] = float(self._umap_cache[idx][0])
                    fe["umap_y"] = float(self._umap_cache[idx][1])
                return fe
        return None

    def _get_neighbours(self, headword: str, lang: str, n: int = 6) -> list[dict]:
        if self._embeddings is None:
            return []
        idx = self._hw_index.get(headword.upper())
        if idx is None:
            return []
        vec  = self._embeddings[idx]
        sims = self._embeddings @ vec
        sims[idx] = -1
        top  = np.argsort(sims)[::-1][:n]
        hw_map = {e["headword"].upper(): e for e in self._entries}
        results = []
        for i in top:
            entry = hw_map.get(self._headwords[i])
            if entry:
                fe = self._format_entry(entry, lang)
                fe["similarity"] = round(float(sims[i]), 4)
                results.append(fe)
        return results

    def cluster_summary(self, lang: str) -> list[dict]:
        from collections import Counter, defaultdict
        by_cluster: dict[int, list] = defaultdict(list)
        for e in self._entries:
            cid = e.get("cluster_id", -1)
            if cid >= 0:
                by_cluster[cid].append(e)
        labels = CLUSTER_LABELS[lang]
        result = []
        for cid in sorted(by_cluster):
            members     = by_cluster[cid]
            tag_counter = Counter(t for e in members for t in e.get("tags", []))
            top_tags    = [
                RHETORICAL_TAG_LABELS[lang].get(t, t)
                for t, _ in tag_counter.most_common(3)
            ]
            result.append({
                "cluster_id":       cid,
                "label":            labels[cid] if cid < len(labels) else f"Cluster {cid}",
                "count":            len(members),
                "top_tags":         top_tags,
                "sample_headwords": [e["headword"] for e in members[:5]],
            })
        return result

    def generate_entry(self, word: str, lang: str) -> dict:
        fr_word = self.translator.to_french(word) if lang == "en" else word
        fr_word = fr_word.strip().upper()

        # Check headword_en fields in both directions to prevent cross-language
        # duplicates: EN mode uses the raw proposed word; FR mode uses it too
        # because someone can type an English word ("ALGORITHM") in FR mode
        # and bypass translation entirely.
        word_upper = word.strip().upper()
        for e in self._entries:
            if e.get("headword_en", "").upper() == word_upper:
                fe = self._format_entry(e, lang)
                fe["already_exists"] = True
                fe["neighbours"] = self._get_neighbours(e["headword"].upper(), lang)
                return fe

        validation = self.validator.validate(fr_word)
        if not validation["valid"]:
            reason = validation["reason"]
            error = f"'{word}' does not appear to be a noun: {reason}"
            return {"error": error, "validation": validation}

        existing = self.get_entry(fr_word, lang)
        if existing:
            existing["already_exists"] = True
            return existing

        neighbours = self._get_neighbours(fr_word, "fr", n=5)
        if not neighbours:
            neighbours = [self._format_entry(e, "fr") for e in self._entries[:5]]

        flaubert_entries = [e for e in self._entries if not e.get("is_generated")]
        try:
            generated_fr = self.generator.generate(fr_word, neighbours, examples=flaubert_entries)
        except Exception as exc:
            return {"error": f"Generation failed ({self.generator.name()}): {exc}"}

        if not generated_fr:
            return {"error": "Generator returned empty text."}

        umap_pt = self._umap_point(generated_fr, lang)
        new_entry = {
            "headword":     fr_word,
            "text":         generated_fr,
            "tags":         [],
            "xrefs":        self._detect_xrefs(generated_fr, fr_word),
            "cluster_id":   umap_pt.get("umap_cluster_id", neighbours[0].get("cluster_id", -1) if neighbours else -1),
            "is_generated": True,
            "generator":    self.generator.name(),
        }
        if lang == "en":
            new_entry["headword_en"] = word.strip().upper()

        result = self._format_entry(new_entry, lang)
        result["neighbours"] = neighbours
        result["generated"]  = True
        result.update(umap_pt)

        # Always include both-language fields so the client can switch UI language
        # without losing the translation.
        if lang == "en":
            result["text_en"]     = result.get("text_translated", "")
        else:
            result["text_en"]     = self.translator.to_english(generated_fr)
            result["headword_en"] = self.translator.to_english(fr_word)

        return result

    def _detect_xrefs(self, text: str, own_headword: str) -> list[str]:
        """Return original-corpus headwords that appear verbatim in generated text."""
        upper_text = text.upper()
        own_upper  = own_headword.upper()
        found: list[str] = []
        # Longest headwords first so multi-word phrases match before their components
        for e in sorted(self._entries, key=lambda e: -len(e["headword"])):
            hw = e["headword"].upper()
            if hw == own_upper or len(hw) < 4:
                continue
            idx = upper_text.find(hw)
            while idx != -1:
                before_ok = idx == 0 or not upper_text[idx - 1].isalpha()
                after_ok  = idx + len(hw) >= len(upper_text) or not upper_text[idx + len(hw)].isalpha()
                if before_ok and after_ok:
                    found.append(e["headword"])
                    break
                idx = upper_text.find(hw, idx + 1)
        return found

    def _umap_point(self, text: str, lang: str) -> dict:
        """Return approximate UMAP coordinates for generated text, used to place it on the map."""
        if self._embeddings is None:
            return {}
        if self._umap_cache is None:
            if UMAP_FILE.exists():
                self._umap_cache = np.load(UMAP_FILE).astype(np.float32)
            else:
                return {}
        coords = self._umap_cache
        vec = self._approximate_vector(text)
        if vec is None:
            return {}
        sims = self._embeddings @ vec
        near_i = int(np.argmax(sims))
        near_xy = coords[near_i]
        near_hw = self._headwords[near_i]
        near_entry = next((e for e in self._entries if e["headword"].upper() == near_hw), None)
        near_cid = near_entry.get("cluster_id", -1) if near_entry else -1
        if not isinstance(near_cid, int):
            near_cid = -1
        labels = CLUSTER_LABELS[lang]
        snippet = text[:70].rsplit(" ", 1)[0] + "…" if len(text) > 70 else text
        return {
            "umap_x":           float(near_xy[0]) + 0.18,
            "umap_y":           float(near_xy[1]) + 0.18,
            "umap_cluster_id":  near_cid,
            "umap_cluster_label": labels[near_cid] if 0 <= near_cid < len(labels) else "",
            "text_snippet":     snippet,
        }
