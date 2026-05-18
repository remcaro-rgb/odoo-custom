# Top-level Makefile for odoo-saas
#
# Convenience targets for common dev / CI ops. Run `make help` for the menu.

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Use docker-compose for local dev unless overridden
COMPOSE ?= docker compose
PYTHON ?= python3.12

# Workspace paths
AGENTS_DIR := agents
SPEC_DIR := docs/superpowers/specs
PLAN_DIR := docs/superpowers/plans

.PHONY: help
help:  ## Show this menu
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2}'

# -----------------------------------------------------------------------------
# Odoo (existing)
# -----------------------------------------------------------------------------

.PHONY: up
up:  ## Start local Odoo + Postgres via docker-compose
	$(COMPOSE) up -d
	@echo "Odoo running at http://localhost:8069"

.PHONY: down
down:  ## Stop local stack
	$(COMPOSE) down

.PHONY: logs
logs:  ## Tail the odoo service logs
	$(COMPOSE) logs -f odoo

.PHONY: shell
shell:  ## Open a psql shell against the local DB
	$(COMPOSE) exec db psql -U odoo -d postgres

# -----------------------------------------------------------------------------
# Agents (Phase 6+)
# -----------------------------------------------------------------------------

.PHONY: agents-install
agents-install:  ## Install the agents package in editable mode + dev deps
	cd $(AGENTS_DIR) && $(PYTHON) -m pip install -e ".[all,dev]"

.PHONY: agents-test
agents-test:  ## Run agents unit + contract tests
	cd $(AGENTS_DIR) && $(PYTHON) -m pytest -v

.PHONY: agents-lint
agents-lint:  ## Lint the agents package
	cd $(AGENTS_DIR) && ruff check . && black --check .

.PHONY: agents-fmt
agents-fmt:  ## Auto-format the agents package
	cd $(AGENTS_DIR) && ruff check --fix . && black .

.PHONY: agents-image
agents-image:  ## Build the agents OCI image
	docker build -t odoo-saas-agents:dev $(AGENTS_DIR)

.PHONY: agents-config-validate
agents-config-validate:  ## Validate agents/config.yml (and reachability of secrets)
	cd $(AGENTS_DIR) && $(PYTHON) -m agents.cli config validate

.PHONY: agents-config-show
agents-config-show:  ## Print resolved agents config (secrets masked)
	cd $(AGENTS_DIR) && $(PYTHON) -m agents.cli config show

.PHONY: agents-smoke
agents-smoke:  ## Run the hello agent end-to-end (proves runtime + adapters)
	cd $(AGENTS_DIR) && $(PYTHON) -m agents.cli run hello --input '{"name": "manu"}'

# -----------------------------------------------------------------------------
# Specs / plans
# -----------------------------------------------------------------------------

.PHONY: new-spec
new-spec:  ## Scaffold a new design spec — usage: make new-spec SLUG=my-feature
	@if [ -z "$(SLUG)" ]; then echo "Usage: make new-spec SLUG=my-feature"; exit 1; fi
	@d=$(SPEC_DIR)/$$(date +%Y-%m-%d)-$(SLUG)-design.md; \
	cp $(SPEC_DIR)/_TEMPLATE-design.md $$d; \
	echo "Created $$d"

.PHONY: new-fix
new-fix:  ## Scaffold a new fix brief — usage: make new-fix SLUG=my-bug
	@if [ -z "$(SLUG)" ]; then echo "Usage: make new-fix SLUG=my-bug"; exit 1; fi
	@d=$(SPEC_DIR)/$$(date +%Y-%m-%d)-$(SLUG)-fix.md; \
	cp $(SPEC_DIR)/_TEMPLATE-fix.md $$d; \
	echo "Created $$d"

.PHONY: new-plan
new-plan:  ## Scaffold a new implementation plan — usage: make new-plan SLUG=my-feature
	@if [ -z "$(SLUG)" ]; then echo "Usage: make new-plan SLUG=my-feature"; exit 1; fi
	@d=$(PLAN_DIR)/$$(date +%Y-%m-%d)-$(SLUG).md; \
	cp $(PLAN_DIR)/_TEMPLATE.md $$d; \
	echo "Created $$d"

.PHONY: list-specs
list-specs:  ## List all specs by date
	@ls -1 $(SPEC_DIR)/*-*.md | grep -v TEMPLATE | sort

# -----------------------------------------------------------------------------
# CI helpers
# -----------------------------------------------------------------------------

.PHONY: ci-validate-workflows
ci-validate-workflows:  ## Lint GitHub Actions workflow YAML
	@which actionlint >/dev/null 2>&1 || { echo "Install actionlint: brew install actionlint"; exit 1; }
	actionlint .github/workflows/*.yml

# -----------------------------------------------------------------------------
# Misc
# -----------------------------------------------------------------------------

.PHONY: addon-list
addon-list:  ## List custom addons
	@ls -1 custom-addons/

.PHONY: addon-test
addon-test:  ## Run tests for one addon — usage: make addon-test ADDON=saas_tenant_gate
	@if [ -z "$(ADDON)" ]; then echo "Usage: make addon-test ADDON=name"; exit 1; fi
	$(COMPOSE) run --rm \
		-e TARGET_DB=ci_$(ADDON) \
		-e INIT_MODULES=$(ADDON) \
		-e STOP_AFTER_INIT=1 \
		odoo --test-enable --test-tags /$(ADDON)

.PHONY: kill-switch-off
kill-switch-off:  ## Flip the agents kill switch OFF
	gh variable set AGENTS_ENABLED --body "false"
	@echo "Agents disabled. Re-enable with: make kill-switch-on"

.PHONY: kill-switch-on
kill-switch-on:  ## Flip the agents kill switch ON
	gh variable set AGENTS_ENABLED --body "true"
	@echo "Agents enabled."
