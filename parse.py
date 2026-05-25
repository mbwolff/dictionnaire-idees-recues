"""
parse.py — Fetch and parse the Dictionnaire des idées reçues from Project
Gutenberg, then tag each entry with rhetorical and enunciative categories
using spaCy morphological and dependency analysis.

The categories draw on speech act theory (Austin, Searle), French enunciative
linguistics (Benveniste, Maingueneau), Ducrot's theory of polyphony and
concession, Barthes' analysis of myth, and direct structural observation of
Flaubert's entries.

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

GUTENBERG_URL = "https://www.gutenberg.org/cache/epub/14156/pg14156.txt"
OUTPUT_FILE   = Path(__file__).parent / "data" / "dictionnaire_entries.json"

# ── Social-performance verbs ──────────────────────────────────────────────────
# Infinitives that, as ROOT of an entry, instruct how to *behave toward*
# the headword concept (Austin's social performatives).
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
    Tags DIR entries with rhetorical and enunciative categories drawn from
    speech act theory (Austin, Searle), French enunciative linguistics
    (Benveniste, Maingueneau), Ducrot's polyphony, Barthes' analysis of myth,
    and direct structural observation of the text.

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

        if re.search(r"\(v\.\s*[^)]+\)", text, re.IGNORECASE) or re.match(r"^V\.\s+", text, re.IGNORECASE):
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
# Guillemet normalisation
# ═════════════════════════════════════════════════════════════════════════════

def _normalize_guillemets(text: str) -> str:
    """Fix OCR closing-guillemet errors and add typographic spaces."""
    # OCR sometimes prints closing » as «: «text« → «text»
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r'«([^«»]*)«', r'«\1»', text)
    text = re.sub(r'«(\S)', r'« \1', text)
    text = re.sub(r'(\S)»', r'\1 »', text)
    return text


# ═════════════════════════════════════════════════════════════════════════════
# Fetch & parse
# ═════════════════════════════════════════════════════════════════════════════

def fetch_text(url: str) -> str:
    print(f"Fetching {url} …")
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(url, context=ctx) as r:
        raw = r.read()
    return raw.decode("utf-8-sig")


def extract_dictionary_section(text: str) -> str:
    start_match = re.search(r"ABELARD|ABSURDE|ACADÉMICIEN|ABSINTHE", text)
    end_match   = re.search(r"End of (the )?Project Gutenberg", text, re.IGNORECASE)
    start = start_match.start() if start_match else 0
    end   = end_match.start()   if end_match   else len(text)
    return text[start:end]


def parse_entries(section: str) -> list[dict]:
    section = section.replace("\r\n", "\n").replace("\r", "\n")
    section = section.replace("‘", "'").replace("’", "'")
    # Preserve «/» guillemets — normalised per-entry by _normalize_guillemets

    headword_re = re.compile(
        r"^([A-ZÀÂÆÇÉÈÊË"
        r"ÎÏÔŒÙÛÜ]"
        r"[A-ZÀÂÆÇÉÈÊË"
        r"ÎÏÔŒÙÛÜ"
        r"a-zàâæçéèêë"
        r"îïôœùûüÿ"
        r" \(\)'.\-_,]{0,90}?)"
        r"[:—–]\s*(.*)$",
        re.MULTILINE,
    )

    def _is_valid_hw(hw_raw: str) -> bool:
        hw_raw = hw_raw.strip().replace("_", "").strip()
        if not hw_raw or len(hw_raw) > 90:
            return False
        # First word must be ALL-CAPS (filters sub-entries like "Viande de cheval:")
        first_word = re.match(
            r"[A-ZÀÂÆÇÉÈÊË"
            r"ÎÏÔŒÙÛÜ"
            r"a-zàâæçéèêë"
            r"îïôœùûüÿ]+",
            hw_raw,
        )
        if not first_word or first_word.group(0) != first_word.group(0).upper():
            return False
        if re.fullmatch(r"[IVXLCDM]+", hw_raw.upper().replace(" ", "")):
            return False
        return True

    all_matches   = list(headword_re.finditer(section))
    valid_matches = [m for m in all_matches if _is_valid_hw(m.group(1))]

    entries = []
    for i, m in enumerate(valid_matches):
        hw_raw = m.group(1).strip().replace("_", "").strip()

        # Use valid_matches for body boundary so invalid matches don't truncate bodies
        body_end = valid_matches[i + 1].start() if i + 1 < len(valid_matches) else len(section)
        body = m.group(2) + " " + section[m.end():body_end]
        body = re.sub(r"\s+", " ", body).strip()
        body = re.sub(r"(\w)- (\w)", r"\1-\2", body)
        body = re.sub(r"\s+[A-Z]$", "", body).strip()  # strip trailing section letter

        if not body:
            continue

        body = _normalize_guillemets(body)

        # Compound headwords "A, B:" → split on comma, keep uppercase-starting parts
        raw_parts = [p.strip() for p in hw_raw.split(",")]
        hw_parts  = [p.replace("_", "").upper() for p in raw_parts
                     if p.strip() and p.strip()[0].isupper()]
        if not hw_parts:
            continue

        xref_raw = re.findall(r"\(v\.\s*([^)]+)\)", body, re.IGNORECASE)
        sm2 = re.match(r"^V\.\s+(.+?)\.?\s*$", body, re.IGNORECASE)
        if sm2:
            xref_raw.append(sm2.group(1))
        xrefs = []
        for raw in xref_raw:
            for part in re.split(r",\s*|\s+et\s+", raw.strip()):
                xrefs.append(part.strip().rstrip(".").upper())

        for hw in hw_parts:
            entries.append({"headword": hw, "text": body, "xrefs": xrefs})

    return entries


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    text    = fetch_text(GUTENBERG_URL)
    section = extract_dictionary_section(text)
    entries = parse_entries(section)

    # Headword renames (Ferrère 1913 and Pléiade 1952 editions vs Gutenberg OCR)
    headword_corrections = {
        "PLIQUE POLONAISE":             "PEIGNE (?) POLONAISE",
        "ABELARD":                      "ABÉLARD",
        "GULF-STREAM":                  "GULF STREAM",
        "PHILIPPE D'ORLÉANS - ÉGALITÉ": "PHILIPPE D'ORLÉANS-ÉGALITÉ",
    }
    # Bare forms created by compound-headword splitting that should be dropped
    drop_headwords = {"ORDRE", "ÉCRIT"}

    corrected = []
    for e in entries:
        if e["headword"] in drop_headwords:
            continue
        e["headword"] = headword_corrections.get(e["headword"], e["headword"])
        corrected.append(e)
    entries = corrected

    # Split sub-entries embedded as "WORD (subst.): …" or "WORD (adj.): …"
    sub_re = re.compile(
        r"\s+([A-ZÀÂÆÇÉÈÊË"
        r"ÎÏÔŒÙÛÜ"
        r"A-Z \(\)'\-]{1,50}?)"
        r"\s*\((subst|adj|adv|verb)\.\):\s*",
        re.IGNORECASE,
    )
    expanded = []
    for e in entries:
        sub_heads = [e["headword"]]
        for sm in sub_re.finditer(e["text"]):
            sub_heads.append(sm.group(1).strip().upper()
                             + " (" + sm.group(2).upper() + ".)")
        if len(sub_heads) > 1:
            parts = sub_re.split(e["text"])
            sub_bodies = [parts[0]]
            for k in range(1, len(parts) - 2, 3):
                sub_bodies.append(parts[k + 2])
            for sh, sb in zip(sub_heads, sub_bodies):
                if sb.strip():
                    expanded.append({"headword": sh, "text": sb.strip(), "xrefs": e["xrefs"]})
        else:
            expanded.append(e)
    entries = expanded

    # Deduplicate on headword (keep first occurrence)
    seen, unique = set(), []
    for e in entries:
        key = e["headword"].upper()
        if key not in seen:
            seen.add(key)
            unique.append(e)

    # Body-text patches: OCR typos confirmed against Ferrère/Pléiade editions
    body_patches = {
        "FEMME":               lambda t: t.replace("Na dites pas", "Ne dites pas"),
        "HALLEBARDE":          lambda t: t.replace("na pas manquer", "ne pas manquer"),
        "HIPPOCRATE":          lambda t: t.replace("Galien dis non", "Galien dit non"),
        "DARTRE":              lambda t: t[0].upper() + t[1:] if t else t,
        "PALLADIUM":           lambda t: t if t.endswith(".") else t + ".",
        "SOMBREUIL (MLLE DE)": lambda t: t[0].upper() + t[1:] if t else t,
        "DICTIONNAIRE":        lambda t: re.sub(
            r"\s*Dictionnaire de rimes.*$", "", t, flags=re.IGNORECASE
        ).strip(),
        # HUSSARD: body extends into HYDRE paragraph (multi-line headword not parsed)
        "HUSSARD":             lambda t: re.sub(
            r"\s+HYDRE de\b.*$", "", t, flags=re.DOTALL | re.IGNORECASE
        ).strip(),
        # AVOCATS: source has :»Oui (backwards opening guillemet — OCR error)
        # After _normalize_guillemets, :» becomes : » (space added), so match that
        "AVOCATS":             lambda t: t.replace(": »Oui", ":« Oui"),
        # FERME (ADJECTIF): source has «roc» . but curated has «roc».
        "FERME (ADJECTIF)":   lambda t: t.replace("roc » .", "roc »."  ),
        # HENRI III / IV: source has no opening «, and trailing « instead of »
        "HENRI III":           lambda t: re.sub(
            r"\s*«\s*$", " »", t.replace("dire: Tous", "dire: « Tous")
        ),
        "HENRI IV":            lambda t: re.sub(
            r"\s*«\s*$", " »", t.replace("dire: Tous", "dire: « Tous")
        ),
    }
    for e in unique:
        patch = body_patches.get(e["headword"])
        if patch:
            e["text"] = patch(e["text"])

    # Manual injections: entries whose headwords cannot be parsed from the source
    hw_set = {e["headword"] for e in unique}
    injections = [
        # HYDRE: headword spans two wrapped lines — unparseable by the regex
        {"headword": "HYDRE DE L'ANARCHIE",  "text": "Tâcher de la vaincre.",   "xrefs": []},
        # DICTIONNAIRE DE RIMES: embedded as lowercase body text in DICTIONNAIRE
        {"headword": "DICTIONNAIRE DE RIMES", "text": "S'en servir? Honteux!", "xrefs": []},
    ]
    for inj in injections:
        if inj["headword"] not in hw_set:
            unique.append(inj)

    # Sort alphabetically by headword
    unique.sort(key=lambda e: e["headword"])

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
