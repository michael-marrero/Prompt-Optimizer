# OSS-02 / D-01 — thin delegator to the portable scripts so make-less environments
# can run ./scripts/*.sh directly. `make setup-dev` is the SOLE owner of `git lfs pull`
# (D-03 deviation from ROADMAP SC#1); `make setup` never pulls LFS.
.PHONY: setup setup-dev dev help
.DEFAULT_GOAL := help

help:  ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n",$$1,$$2}'

setup:  ## Provision to run the app (no LFS pull — D-03)
	./scripts/setup.sh

setup-dev:  ## Provision for retraining (adds git lfs pull + HF prefetch — D-03)
	./scripts/setup-dev.sh

dev:  ## Launch FastAPI + Next together (Ctrl-C stops both)
	./scripts/dev.sh
