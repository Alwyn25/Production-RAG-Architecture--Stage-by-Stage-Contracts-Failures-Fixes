.PHONY: install test audit

AUDIT_DIR := eval/audits/post-00

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest -q

# Requires traces from the post-01 baseline on the eval v1 dev split (see $(AUDIT_DIR)/README.md)
audit:
	python $(AUDIT_DIR)/failure_attribution.py \
		--traces $(AUDIT_DIR)/traces.jsonl \
		--docs $(AUDIT_DIR)/parsed_docs.jsonl \
		$(if $(wildcard $(AUDIT_DIR)/human_labels.csv),--labels $(AUDIT_DIR)/human_labels.csv,)
