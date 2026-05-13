"""
parse.py — Fetch and parse the Dictionnaire des idées reçues from Project
Gutenberg, then tag each entry with Herschberg-Pierrot's enunciative
categories using spaCy morphological and dependency analysis.

Requirements:
    pip install spacy
    python -m spacy download fr_core_news_sm

Output: data/dictionnaire_entries.json

Run from repo root:
    python parse.py
"""

import re
import json
import urllib.request
from pathlib import Path

GUTENBERG_URL = "https://www.gutenberg.org/files/6056/6056-0.txt"
OUTPUT_FILE   = Path(__file__).parent / "data" / "dictionnaire_entries.json"

# ── Social-performance verbs ──────────────────────────────────────────────────
# Infinitives that, as ROOT of an entry, instruct how to *behave toward*
# the headword concept — Herschberg-Pierrot's "impératif social".
SOCIAL_PERFORMANCE_VERBS = {
    "rire", "tonner", "mépriser", "admirer", "s'extasier", "affecter",
    "railler", "vanter", "déplorer", "éviter", "consulter", "parler",
    "citer", "plaindre", "exalter", "critiquer", "moquer", "louer",
    "blâmer", "respecter", "employer", "lire", "voir", "connaître",
    "ignorer", "croire", "douter", "s'abstenir", "prétendre", "feindre",
}

# ── Existence verbs (for mythification) ──────────────────────────────────────
EXISTENCE_VERBS = {
    "exister", "vivre", "être", "naître", "mourir", "se passer", "arriver",
}

# ── Concessive conjunctions (for self_undermining) ───────────────────────────
CONCESSIVE = {"mais", "cependant", "pourtant", "néanmoins", "toutefois", "or"}

# ── Danger vocabulary ─────────────────────────────────────────────────────────
DANGER_LEXICON = {
    "poison", "mortel", "mortelle", "fatal", "fatale", "dangereux",
    "dangereuse", "pernicieux", "pernicieuse", "nocif", "nocive",
    "funeste", "terrible", "redoutable", "épouvantable",
}


# ═════════════════════════════════════════════════════════════════════════════
# spaCy enunciative tagger
# ═════════════════════════════════════════════════════════════════════════════

class EnunciativeTagger:
    """
    Tags DIR entries with Herschberg-Pierrot's enunciative categories.

    Tags (not mutually exclusive):

    prescriptive_imperative
        Entry is phrased as an instruction to the bourgeois reader.
        Detected: ROOT infinitive verb OR conjugated imperative OR
        être-copula + predicate noun with no overt subject.

    social_performance
        Prescriptive imperative whose verb is a verb of social behaviour
        toward the headword concept (rire, tonner, mépriser, admirer…).

    verite_generale
        Impersonal present-tense assertion of universal truth.
        Detected: present indicative ROOT with zero or impersonal subject;
        être-copula constructions with zero subject; falloir + inf;
        ROOT adjective with no overt subject.

    self_undermining
        Concessive structure where two propositions contradict each other.
        Detected: CCONJ from CONCESSIVE set linking two verbal expressions.

    mythification
        Denial of historical existence.
        Detected: negation + past participle of an existence verb, or
        negated present of exister/vivre.

    circular_definition
        Headword lemma reappears in the body.

    superlative_assertion
        Superlative adjective/adverb asserting an absolute property.
        Detected: plus/moins as advmod to an adjective.

    danger_assertion
        Entry asserts the headword is dangerous or deadly.
        Detected: lemma match against DANGER_LEXICON.

    nominal_assertion
        Entry consists of a noun/adjective phrase with no finite verb —
        Flaubert's most compressed form.
        "Cause de la dégénérescence de la race."

    cross_reference
        Explicit (Voir X) link to another entry.
    """

    def __init__(self):
        import spacy
        try:
            self._nlp = spacy.load("fr_core_news_sm")
            print("[Tagger] spaCy fr_core_news_sm loaded.")
        except OSError:
            raise RuntimeError(
                "spaCy model not found.\n"
                "Run: python -m spacy download fr_core_news_sm"
            )

    def tag(self, headword: str, text: str) -> list[str]:
        doc  = self._nlp(text)
        tags = set()

        if re.search(r"\(Voir\s+.+?\)", text, re.IGNORECASE):
            tags.add("cross_reference")

        if self._is_prescriptive_imperative(doc):
            tags.add("prescriptive_imperative")

        if self._is_social_performance(doc):
            tags.add("social_performance")
            tags.add("prescriptive_imperative")

        if self._is_verite_generale(doc):
            tags.add("verite_generale")

        if self._is_self_undermining(doc):
            tags.add("self_undermining")

        if self._is_mythification(doc):
            tags.add("mythification")

        if self._is_circular(headword, doc):
            tags.add("circular_definition")

        if self._is_superlative(doc):
            tags.add("superlative_assertion")

        if self._is_danger(doc):
            tags.add("danger_assertion")

        if self._is_nominal_assertion(doc):
            tags.add("nominal_assertion")

        return sorted(tags)

    # ── Individual detectors ──────────────────────────────────────────────────

    def _is_prescriptive_imperative(self, doc) -> bool:
        for sent in doc.sents:
            for t in sent:
                m = str(t.morph)
                if t.pos_ == "VERB" and "VerbForm=Inf" in m and t.dep_ in ("ROOT", "conj"):
                    return True
                if t.pos_ == "VERB" and "Mood=Imp" in m:
                    return True
                # rire, tonner etc. sometimes parsed as NOUN by spaCy
                if (t.pos_ == "NOUN" and t.dep_ == "ROOT"
                        and t.lemma_.lower() in SOCIAL_PERFORMANCE_VERBS
                        and not any(c.dep_ == "det" for c in t.children)):
                    return True
        return False

    def _is_social_performance(self, doc) -> bool:
        for sent in doc.sents:
            for t in sent:
                lemma = t.lemma_.lower()
                if lemma not in SOCIAL_PERFORMANCE_VERBS:
                    continue
                if (t.dep_ in ("ROOT", "conj")
                        and t.pos_ == "VERB"
                        and "VerbForm=Inf" in str(t.morph)):
                    return True
                if (t.pos_ == "NOUN" and t.dep_ == "ROOT"
                        and not any(c.dep_ == "det" for c in t.children)):
                    return True
        return False

    def _is_verite_generale(self, doc) -> bool:
        for sent in doc.sents:
            for t in sent:
                m = str(t.morph)

                # Pattern A: ROOT verb, present indicative, zero/impersonal subject
                if (t.pos_ == "VERB" and "Mood=Ind" in m
                        and "Tense=Pres" in m and t.dep_ == "ROOT"):
                    subjs = [c for c in t.children if c.dep_ in ("nsubj", "expl:subj")]
                    if not subjs:
                        return True
                    for s in subjs:
                        if s.lemma_.lower() in ("on", "il", "tout", "personne",
                                                 "chacun", "nul", "rien"):
                            return True

                # Pattern B: être as cop + zero subject (headword ellipsis)
                # "N'est jamais en équilibre." — être is cop, noun is ROOT
                if (t.lemma_ == "être" and t.dep_ == "cop" and "Tense=Pres" in m):
                    if not any(c.dep_ in ("nsubj", "expl:subj") for c in t.head.children):
                        return True

                # Pattern C: il faut + inf
                if t.lemma_ == "falloir" and t.dep_ == "ROOT":
                    return True

                # Pattern D: ROOT adjective with no overt subject
                # "Toujours honnêtes quand ils ne sont pas à l'émeute."
                if t.pos_ == "ADJ" and t.dep_ == "ROOT":
                    if not any(c.dep_ in ("nsubj", "expl:subj") for c in t.children):
                        return True

        return False

    def _is_self_undermining(self, doc) -> bool:
        def is_verbal(t):
            return (
                (t.pos_ in ("VERB", "AUX") and "VerbForm=Fin" in str(t.morph))
                or (t.pos_ == "PRON" and t.dep_ == "conj")
                or (t.pos_ == "ADV" and t.dep_ == "ROOT"
                    and any(c.dep_ == "obj" for c in t.children))
            )

        for sent in doc.sents:
            for t in sent:
                if t.pos_ == "CCONJ" and t.lemma_.lower() in CONCESSIVE:
                    # Strategy A: direct conj dependency
                    if any(c.dep_ == "conj" for c in t.head.children):
                        return True
                    # Strategy B: verbal content on both sides
                    lv = [x for x in sent if x.i < t.i and is_verbal(x)]
                    rv = [x for x in sent if x.i > t.i and is_verbal(x)]
                    if lv and rv:
                        return True
        return False

    def _is_mythification(self, doc) -> bool:
        has_neg = any(
            "Polarity=Neg" in str(t.morph) or t.lemma_ in ("jamais", "point")
            for t in doc
        )
        if not has_neg:
            return False
        for t in doc:
            m = str(t.morph)
            if ("VerbForm=Part" in m and "Tense=Past" in m
                    and t.lemma_.lower() in EXISTENCE_VERBS):
                return True
            if (t.lemma_.lower() in ("exister", "vivre") and t.pos_ == "VERB"
                    and any("Polarity=Neg" in str(c.morph)
                            or c.lemma_ in ("jamais", "pas", "point")
                            for c in t.children)):
                return True
        return False

    def _is_circular(self, headword: str, doc) -> bool:
        hw_doc    = self._nlp(headword.lower())
        hw_lemmas = {
            t.lemma_.lower() for t in hw_doc
            if t.pos_ not in ("PUNCT", "DET", "ADP") and len(t.lemma_) > 2
        }
        if not hw_lemmas:
            return False
        body_lemmas = {
            t.lemma_.lower() for t in doc
            if t.pos_ not in ("PUNCT", "DET", "ADP")
        }
        return bool(hw_lemmas & body_lemmas)

    def _is_superlative(self, doc) -> bool:
        for t in doc:
            if (t.lemma_ in ("plus", "moins") and t.pos_ == "ADV"
                    and t.dep_ in ("advmod", "fixed", "amod")):
                if t.head.pos_ == "ADJ":
                    return True
                if any(c.pos_ == "ADJ" for c in t.head.children):
                    return True
            if "Degree=Sup" in str(t.morph):
                return True
        return False

    def _is_danger(self, doc) -> bool:
        return any(t.lemma_.lower() in DANGER_LEXICON for t in doc)

    def _is_nominal_assertion(self, doc) -> bool:
        has_finite = any(
            "VerbForm=Fin" in str(t.morph)
            for t in doc if t.pos_ in ("VERB", "AUX")
        )
        if has_finite:
            return False
        return any(
            t.dep_ == "ROOT" and t.pos_ in ("NOUN", "ADJ", "PROPN")
            for t in doc
        )


# ═════════════════════════════════════════════════════════════════════════════
# Fetch & parse
# ═════════════════════════════════════════════════════════════════════════════

def fetch_text(url: str) -> str:
    print(f"Fetching {url} …")
    with urllib.request.urlopen(url) as r:
        raw = r.read()
    return raw.decode("utf-8-sig")


def extract_dictionary_section(text: str) -> str:
    start_match = re.search(r"ABSURDE|ACADÉMICIEN|ABSINTHE", text)
    end_match   = re.search(r"End of (the )?Project Gutenberg", text, re.IGNORECASE)
    start = start_match.start() if start_match else 0
    end   = end_match.start()   if end_match   else len(text)
    return text[start:end]


def parse_entries(section: str) -> list[dict]:
    section = section.replace("\r\n", "\n").replace("\r", "\n")
    section = section.replace("\u2018", "'").replace("\u2019", "'")
    section = section.replace("\u00ab", '"').replace("\u00bb", '"')

    headword_re = re.compile(
        r"^([A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜ][A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜ\s\(\)'\-]{1,60?})"
        r"[\.—\-–]\s*(.*)$",
        re.MULTILINE,
    )

    entries  = []
    matches  = list(headword_re.finditer(section))

    for i, m in enumerate(matches):
        headword = m.group(1).strip().rstrip(".")
        if len(headword) > 50:
            continue

        body_start = m.end()
        body_end   = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        body       = m.group(2) + " " + section[body_start:body_end]
        body       = re.sub(r"\s+", " ", body).strip()

        if not body:
            continue

        xrefs = re.findall(r"\(Voir\s+([^)]+)\)", body, re.IGNORECASE)
        xrefs = [x.strip().rstrip(".") for x in xrefs]

        entries.append({"headword": headword, "text": body, "xrefs": xrefs})

    return entries


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    text    = fetch_text(GUTENBERG_URL)
    section = extract_dictionary_section(text)
    entries = parse_entries(section)

    # Deduplicate on headword
    seen, unique = set(), []
    for e in entries:
        key = e["headword"].upper()
        if key not in seen:
            seen.add(key)
            unique.append(e)

    print(f"Parsed {len(unique)} entries. Running spaCy enunciative tagger…")

    tagger    = EnunciativeTagger()
    tag_counts: dict[str, int] = {}
    untagged  = 0

    for e in unique:
        e["tags"] = tagger.tag(e["headword"], e["text"])
        for t in e["tags"]:
            tag_counts[t] = tag_counts.get(t, 0) + 1
        if not e["tags"]:
            untagged += 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(unique, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nSaved → {OUTPUT_FILE}")
    print(f"\n── Tag distribution ──────────────────────────────────")
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        bar = "█" * (count // 2)
        print(f"  {tag:30s} {count:3d}  {bar}")
    print(f"  {'(untagged)':30s} {untagged:3d}")

    print(f"\n── Sample entries ────────────────────────────────────")
    for e in unique[:6]:
        print(f"\n  [{e['headword']}]")
        print(f"    {e['text'][:90]}")
        print(f"    tags: {e['tags']}")


if __name__ == "__main__":
    main()
