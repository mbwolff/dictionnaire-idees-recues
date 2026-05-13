# Dictionnaire des idées reçues — Flask App

A bilingual (FR/EN) web application for browsing Flaubert's satirical dictionary
and generating new entries in his style using word embeddings and Claude.

## Setup

```bash
pip install -r requirements.txt
python -m spacy download fr_core_news_sm
```

## Data

Copy the pipeline outputs into `data/`:

```
dictionnaire_app/
  data/
    dictionnaire_entries.json   ← from 01_parse.py
    embeddings.npz              ← from 02_embed.py (enables semantic search)
    new_entries.json            ← auto-created on first generation
```

The app runs without `embeddings.npz` — semantic search falls back to text search.

## Run

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python app.py
# → http://localhost:5050
```

Port 5050 is used because macOS Control Center's AirPlay Receiver squats on
port 5000 and answers requests with `403 Forbidden`.

For production:
```bash
gunicorn -w 2 -b 0.0.0.0:5050 app:app
```

## Features

| Feature | Description |
|---|---|
| Text search | Substring search on headword and entry text |
| Semantic search | Cosine similarity on French embeddings (requires embeddings.npz) |
| FR/EN toggle | Switch UI and translations at any time |
| Light/dark mode | Follows system preference; toggle in header |
| Browse | Alphabetical index + paginated entry list |
| Themes | Semantic cluster browser |
| Add entry | Validate as French noun → generate in Flaubert's style → persist |
| Neighbours | Six most semantically similar entries shown per entry |

## Architecture

```
app.py          Flask routes
pipeline.py     Embedding search · noun validation · translation · generation
templates/      Jinja2 HTML
static/css/     Editorial typographic stylesheet
static/js/      Single-page app logic (vanilla JS)
data/           Dictionary JSON + embeddings
```

## Noun validation

Uses spaCy `fr_core_news_sm`. Accepted POS tags: `NOUN`, `PROPN`, `X` (rare/foreign words).
Falls back to a regex heuristic if spaCy is not installed.

## Translation

Uses `deep-translator` (Google Translate, free tier, no API key required).
Results are cached in memory per session. The French entry text is always
preserved as the canonical version; translations are display-only.
