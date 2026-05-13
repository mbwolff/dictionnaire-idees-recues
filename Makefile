# ══════════════════════════════════════════════════════════════════
# Dictionnaire des idées reçues — Makefile
# ══════════════════════════════════════════════════════════════════
#
# Usage:
#   make install      install Python dependencies + spaCy model
#   make pipeline     parse → embed → cluster  (run once to build data/)
#   make run          start the Flask app
#   make clean        remove generated data files
#
# Generator backend (set via env var, default: ollama):
#   make run GENERATOR=ollama OLLAMA_MODEL=mistral
#   make run GENERATOR=transformers HF_MODEL=microsoft/Phi-3-mini-4k-instruct
#   make run GENERATOR=claude ANTHROPIC_API_KEY=sk-ant-...
# ══════════════════════════════════════════════════════════════════

PYTHON       ?= python3
GENERATOR    ?= ollama
OLLAMA_MODEL ?= mistral
HF_MODEL     ?= mistralai/Mistral-7B-Instruct-v0.3
PORT         ?= 5050

DATA_DIR  = data
ENTRIES   = $(DATA_DIR)/dictionnaire_entries.json
EMBEDDINGS= $(DATA_DIR)/embeddings.npz
CLUSTERS  = $(DATA_DIR)/clusters.json

.PHONY: all install pipeline parse embed cluster run clean

all: install pipeline run

# ── Setup ─────────────────────────────────────────────────────────

install:
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m spacy download fr_core_news_sm
	@echo ""
	@echo "If using Ollama (default generator):"
	@echo "  1. Install from https://ollama.com"
	@echo "  2. Run: ollama pull $(OLLAMA_MODEL)"

# ── Pipeline ──────────────────────────────────────────────────────

pipeline: parse embed cluster
	@echo ""
	@echo "✓ Pipeline complete. Run 'make run' to start the app."

parse: $(ENTRIES)
$(ENTRIES):
	@mkdir -p $(DATA_DIR)
	$(PYTHON) parse.py

embed: $(EMBEDDINGS)
$(EMBEDDINGS): $(ENTRIES)
	$(PYTHON) embed.py

cluster: $(CLUSTERS)
$(CLUSTERS): $(EMBEDDINGS)
	$(PYTHON) cluster.py

# ── App ───────────────────────────────────────────────────────────

run: $(ENTRIES)
	GENERATOR=$(GENERATOR) \
	OLLAMA_MODEL=$(OLLAMA_MODEL) \
	HF_MODEL=$(HF_MODEL) \
	PORT=$(PORT) \
	$(PYTHON) app.py

# ── Maintenance ───────────────────────────────────────────────────

clean:
	rm -f $(DATA_DIR)/dictionnaire_entries.json \
	      $(DATA_DIR)/embeddings.npz \
	      $(DATA_DIR)/clusters.json \
	      $(DATA_DIR)/gap_candidates.json
	rm -rf reports/
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
