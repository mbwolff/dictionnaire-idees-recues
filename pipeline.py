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
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import numpy as np

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
ENTRIES_FILE    = BASE_DIR / "data" / "dictionnaire_entries.json"
EMBEDDINGS_FILE = BASE_DIR / "data" / "embeddings.npz"
NEW_ENTRIES_FILE= BASE_DIR / "data" / "new_entries.json"

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
        "Types sociaux & passions", "Conventions, corps & bienséance", "Arts, société & plaisirs",
        "Langage & bon usage", "Vie bourgeoise & formules", "Usages, apparences & antiquité",
        "Arts, séduction & culture", "Polémiques & conflits", "Patrie, religion & nature",
        "Nations & corps de métiers", "Dérision & attitudes", "Sciences, figures & institutions",
    ],
    "en": [
        "Social Types & Passions", "Conventions, Body & Propriety", "Arts, Society & Pleasures",
        "Language & Proper Usage", "Bourgeois Life & Stock Phrases", "Customs, Appearances & Antiquity",
        "Arts, Seduction & Culture", "Polemics & Conflict", "Homeland, Religion & Nature",
        "Nations & Trades", "Derision & Attitudes", "Sciences, Figures & Institutions",
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


def build_user_prompt(headword: str, neighbours: list[dict]) -> str:
    neighbour_block = "\n".join(
        f"  {n['headword'].upper()}. {n['text']}" for n in neighbours[:5]
    )
    return (
        f"{FEW_SHOT}\n\n"
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
    def generate(self, headword: str, neighbours: list[dict]) -> str: ...

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

    def generate(self, headword: str, neighbours: list[dict]) -> str:
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
                {"role": "user",   "content": build_user_prompt(headword, neighbours)},
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

    def generate(self, headword: str, neighbours: list[dict]) -> str:
        self._load()
        # Mistral-style instruction format; works for most instruct-tuned models
        prompt = (
            f"<s>[INST] {SYSTEM_PROMPT}\n\n"
            f"{build_user_prompt(headword, neighbours)} [/INST]"
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

    def generate(self, headword: str, neighbours: list[dict]) -> str:
        if not ANTHROPIC_API_KEY:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

        payload = json.dumps({
            "model":      CLAUDE_MODEL,
            "max_tokens": 200,
            "system":     SYSTEM_PROMPT,
            "messages":   [{"role": "user", "content": build_user_prompt(headword, neighbours)}],
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
        if not self._VOWEL_RE.search(word):
            return {"valid": False, "pos": "", "lemma": word.upper(),
                    "reason": f"'{word}' does not look like a word."}
        # Reject repetitive patterns (ABABA, ABABABA…): real words longer than
        # 4 letters always use more than 2 distinct characters.
        core = re.sub(r"[\s\-']", "", word.upper())
        if len(core) > 4 and len(set(core)) <= 2:
            return {"valid": False, "pos": "", "lemma": word.upper(),
                    "reason": f"'{word}' does not look like a word."}
        return self._validate_spacy(word) if self._nlp else self._validate_heuristic(word)

    def _validate_spacy(self, word: str) -> dict:
        doc   = self._nlp(word)
        token = doc[0]
        pos   = token.pos_
        lemma = token.lemma_.upper()
        if pos in ("NOUN", "PROPN"):
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
        self._new_entries: list[dict]  = []
        self._embeddings: Optional[np.ndarray] = None
        self._headwords: list[str]     = []
        self._hw_index: dict[str, int] = {}
        self._sentence_model           = None
        self._tsne_cache: Optional[np.ndarray] = None
        self._load_data()

    def _load_data(self):
        if ENTRIES_FILE.exists():
            self._entries = json.loads(ENTRIES_FILE.read_text("utf-8"))
            print(f"[Pipeline] {len(self._entries)} Flaubert entries loaded.")
        else:
            print(f"[Pipeline] WARNING: {ENTRIES_FILE} not found. Run 01_parse.py first.")

        if NEW_ENTRIES_FILE.exists():
            self._new_entries = json.loads(NEW_ENTRIES_FILE.read_text("utf-8"))
            print(f"[Pipeline] {len(self._new_entries)} generated entries loaded.")

        if EMBEDDINGS_FILE.exists():
            npz = np.load(EMBEDDINGS_FILE, allow_pickle=True)
            self._embeddings = npz["embeddings"].astype(np.float32)
            self._headwords  = [h.upper() for h in npz["headwords"]]
            self._hw_index   = {hw: i for i, hw in enumerate(self._headwords)}
            print(f"[Pipeline] Embeddings: {self._embeddings.shape}")
        else:
            print("[Pipeline] No embeddings — semantic search will fall back to text search.")

    def _format_entry(self, entry: dict, lang: str) -> dict:
        text = entry.get("text", "")
        hw   = entry.get("headword", "")
        cid  = entry.get("cluster_id", -1)
        result = {
            "headword":      hw,
            "text":          text,
            "tags":          entry.get("tags", []),
            "xrefs":         entry.get("xrefs", []),
            "cluster_id":    cid,
            "cluster_label": (
                CLUSTER_LABELS[lang][cid]
                if 0 <= cid < len(CLUSTER_LABELS["fr"]) else ""
            ),
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
        return len(self._entries) + len(self._new_entries)

    def stats(self) -> dict:
        return {
            "flaubert_entries":  len(self._entries),
            "generated_entries": len(self._new_entries),
            "embeddings_loaded": self._embeddings is not None,
            "clusters":          len(CLUSTER_LABELS["fr"]),
            "generator":         self.generator.name(),
        }

    def tsne_data(self, lang: str) -> list[dict]:
        if self._embeddings is None:
            return []
        if self._tsne_cache is None:
            from sklearn.manifold import TSNE
            print("[Pipeline] Computing t-SNE…")
            coords = TSNE(
                n_components=2, random_state=42, perplexity=30,
                max_iter=1000, init="pca", learning_rate="auto",
            ).fit_transform(self._embeddings)
            self._tsne_cache = coords.astype(np.float32)
            print("[Pipeline] t-SNE done.")
        coords = self._tsne_cache
        labels = CLUSTER_LABELS[lang]
        result = []
        for i, e in enumerate(self._entries):
            if i >= len(coords):
                break
            cid = e.get("cluster_id", -1)
            hw  = e["headword"]
            result.append({
                "headword":         hw,
                "headword_display": e.get("headword_en", hw) if lang == "en" else hw,
                "x":                float(coords[i][0]),
                "y":                float(coords[i][1]),
                "cluster_id":       cid,
                "cluster_label":    labels[cid] if 0 <= cid < len(labels) else "",
            })
        return result

    def recent_generated(self, limit: int, lang: str) -> list[dict]:
        recent = list(reversed(self._new_entries[-limit:]))
        return [self._format_entry({**e, "is_generated": True}, lang) for e in recent if "headword" in e]

    def all_entries(self, start: int, limit: int, lang: str) -> list[dict]:
        all_e = self._entries + [
            {**e, "is_generated": True} for e in self._new_entries if "headword" in e
        ]
        all_e.sort(key=lambda x: x.get("headword", ""))
        return [self._format_entry(e, lang) for e in all_e[start:start + limit]]

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

    def cluster_search(self, cluster_id: int, limit: int, lang: str) -> list[dict]:
        all_e = self._entries + [{**e, "is_generated": True} for e in self._new_entries if "headword" in e]
        results = [self._format_entry(e, lang) for e in all_e if e.get("cluster_id") == cluster_id]
        results.sort(key=lambda x: x["headword"])
        return results[:limit]

    def prefix_search(self, prefix: str, limit: int, lang: str) -> list[dict]:
        p = prefix.upper()
        all_e = self._entries + [{**e, "is_generated": True} for e in self._new_entries if "headword" in e]
        results = [self._format_entry(e, lang) for e in all_e if e.get("headword", "").upper().startswith(p)]
        results.sort(key=lambda x: x["headword"])
        return results[:limit]

    def text_search(self, query: str, limit: int, lang: str) -> list[dict]:
        q = query.upper()
        all_e = self._entries + [{**e, "is_generated": True} for e in self._new_entries if "headword" in e]
        results = []
        for e in all_e:
            if q in e.get("headword", "").upper() or q in e.get("text", "").upper():
                results.append(self._format_entry(e, lang))
                if len(results) >= limit:
                    break
        return results

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
                return fe
        for e in self._new_entries:
            if e.get("headword", "").upper() == hw:
                fe = self._format_entry({**e, "is_generated": True}, lang)
                fe["neighbours"] = self._get_neighbours(hw, lang)
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
        for e in self._entries + list(self._new_entries):
            if e.get("headword_en", "").upper() == word_upper:
                fe = self._format_entry(e, lang)
                fe["already_exists"] = True
                fe["neighbours"] = self._get_neighbours(e["headword"].upper(), lang)
                return fe

        validation = self.validator.validate(fr_word)
        if not validation["valid"]:
            return {
                "error": f"'{word}' does not appear to be a noun: {validation['reason']}",
                "validation": validation,
            }

        existing = self.get_entry(fr_word, lang)
        if existing:
            existing["already_exists"] = True
            return existing

        neighbours = self._get_neighbours(fr_word, "fr", n=5)
        if not neighbours:
            neighbours = [self._format_entry(e, "fr") for e in self._entries[:5]]

        try:
            generated_fr = self.generator.generate(fr_word, neighbours)
        except Exception as exc:
            return {"error": f"Generation failed ({self.generator.name()}): {exc}"}

        if not generated_fr:
            return {"error": "Generator returned empty text."}

        new_entry = {
            "headword":     fr_word,
            "text":         generated_fr,
            "tags":         [],
            "xrefs":        [],
            "cluster_id":   neighbours[0].get("cluster_id", -1) if neighbours else -1,
            "is_generated": True,
            "generator":    self.generator.name(),
        }
        if lang == "en":
            new_entry["headword_en"] = word.strip().upper()
        self._new_entries.append(new_entry)
        NEW_ENTRIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        NEW_ENTRIES_FILE.write_text(
            json.dumps(self._new_entries, ensure_ascii=False, indent=2), "utf-8"
        )

        result = self._format_entry(new_entry, lang)
        result["neighbours"] = neighbours
        result["generated"]  = True
        return result
