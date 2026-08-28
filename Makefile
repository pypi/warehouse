DB := example
IPYTHON := no

# set environment variable WAREHOUSE_IPYTHON_SHELL=1 if IPython
# needed in development environment
ifeq ($(WAREHOUSE_IPYTHON_SHELL), 1)
    IPYTHON = yes
endif

# Optimization: if the user explicitly passes tests via `T`,
# disable xdist (since the overhead of spawning workers is typically
# higher than running a small handful of specific tests).
# Only do this when the user doesn't set any explicit `TESTARGS` to avoid
# confusion.
COVERAGE := yes
ifneq ($(T),)
		COVERAGE = no
		ifeq ($(TESTARGS),)
				TESTARGS = -n 0
		endif
endif

# PEP 669 introduced sys.monitoring, a lighter-weight way to monitor
# the execution. While this introduces significant speed-up during test
# execution, coverage does not yet support dynamic contexts when enabled.
# This variable can be set to other tracers (ctrace, pytrace, sysmon).
# https://nedbatchelder.com/blog/202312/coveragepy_with_sysmonitoring.html
# TODO: Flip to `sysmon` when we're on Python 3.14
COVERAGE_CORE ?= ctrace

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available commands
	@awk 'BEGIN {FS = ":.*##"; printf "Warehouse development commands\n\nUsage:\n  make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z0-9_.-]+:.*##/ {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2} \
		/^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)}' $(MAKEFILE_LIST)

.state/docker-build-base: Dockerfile package.json package-lock.json requirements/main.txt requirements/deploy.txt requirements/lint.txt requirements/tests.txt requirements/dev.txt
	# Build our base container for this project.
	docker compose build --build-arg IPYTHON=$(IPYTHON) --force-rm base

	# Mark the state so we don't rebuild this needlessly.
	mkdir -p .state
	touch .state/docker-build-base

.state/docker-build-static: Dockerfile package.json package-lock.json babel.config.js
	# Build our static container for this project.
	docker compose build --force-rm static

	# Mark the state so we don't rebuild this needlessly.
	mkdir -p .state
	touch .state/docker-build-static

.state/docker-build-docs: Dockerfile requirements/docs-dev.txt requirements/docs-blog.txt requirements/docs-user.txt
	# Build the worker container for this project
	docker compose build --build-arg  USER_ID=$(shell id -u)  --build-arg GROUP_ID=$(shell id -g) --force-rm dev-docs

	# Mark the state so we don't rebuild this needlessly.
	mkdir -p .state
	touch .state/docker-build-docs

.state/docker-build: .state/docker-build-base .state/docker-build-static .state/docker-build-docs
	# Build the worker container for this project
	docker compose build --force-rm worker

	# Mark the state so we don't rebuild this needlessly.
	mkdir -p .state
	touch .state/docker-build

##@ Build & Serve

build: ## Build all development containers
	@$(MAKE) .state/docker-build

	docker system prune -f --filter "label=com.docker.compose.project=warehouse"

serve: .state/docker-build ## Start Warehouse and its dependencies
	$(MAKE) .state/db-populated
	$(MAKE) .state/search-indexed
	docker compose up --remove-orphans

debug: .state/docker-build-base ## Start the web service in debug mode
	docker compose run --rm --service-ports web

shell: .state/docker-build-base ## Open a Warehouse Python shell
	docker compose run --rm web python -m warehouse shell

totp: .state/docker-build-base ## Generate a dev TOTP code
	@docker compose run --rm base bin/devtotp

##@ Testing & Quality

tests: .state/docker-build-base ## Run Python tests; use T=path/to/test.py
	docker compose run --rm --env COVERAGE=$(COVERAGE) --env COVERAGE_CORE=$(COVERAGE_CORE) tests bin/tests --postgresql-host db $(T) $(TESTARGS)

static_tests: .state/docker-build-static ## Run static asset tests
	docker compose run --rm static bin/static_tests $(T) $(TESTARGS)

static_pipeline: .state/docker-build-static ## Build the static asset pipeline
	docker compose run --rm static bin/static_pipeline $(T) $(TESTARGS)

reformat: .state/docker-build-base ## Reformat source files
	docker compose run --rm base bin/reformat

lint: .state/docker-build-base .state/docker-build-static ## Run Python and static linters
	docker compose run --rm base bin/lint
	docker compose run --rm static bin/static_lint

##@ Documentation

dev-docs: .state/docker-build-docs ## Build developer documentation
	docker compose run --rm dev-docs bin/dev-docs

dev-docs-serve: .state/docker-build-docs ## Serve developer documentation
	docker compose up dev-docs

user-docs: .state/docker-build-docs ## Build user documentation
	docker compose run --rm user-docs bin/user-docs

user-docs-serve: .state/docker-build-docs ## Serve user documentation
	docker compose up user-docs

blog: .state/docker-build-docs ## Build the blog
	docker compose run --rm blog mkdocs build -f docs/mkdocs-blog.yml

blog-serve: .state/docker-build-docs ## Serve the blog
	docker compose up blog

##@ Dependencies & Maintenance

licenses: .state/docker-build-base ## Check dependency licenses
	docker compose run --rm base bin/licenses

deps: .state/docker-build-base ## Check for outdated dependencies
	docker compose run --rm base bin/deps

deps_upgrade_all: .state/docker-build-base ## Upgrade all dependencies
	docker compose run --rm base bin/deps-upgrade -a

deps_upgrade_project: .state/docker-build-base ## Upgrade dependencies for one project; use P=name
	docker compose run --rm base bin/deps-upgrade -p $(P)

translations: .state/docker-build-base ## Update translation catalogs
	docker compose run --rm base bin/translations

patch: .state/docker-build-base ## Apply local patches
	docker compose run --rm base bin/patch

requirements/%.txt: requirements/%.in
	docker compose run --rm base pip-compile --generate-hashes --output-file=$@ $<

##@ Database

resetdb: .state/docker-build-base ## Reset and repopulate the database
	docker compose pause web worker
	docker compose up -d db
	docker compose exec --user postgres db /docker-entrypoint-initdb.d/init-dbs.sh
	rm -f .state/db-populated .state/db-migrated
	$(MAKE) initdb
	docker compose unpause web worker

.state/search-indexed: .state/db-populated
	$(MAKE) reindex
	mkdir -p .state && touch .state/search-indexed

.state/db-populated: .state/db-migrated
	docker compose run --rm web python -m warehouse sponsors populate-db
	docker compose run --rm web python -m warehouse classifiers sync
	docker compose exec --user postgres db psql -U postgres warehouse -f /post-migrations.sql
	mkdir -p .state && touch .state/db-populated

.state/db-migrated: .state/docker-build-base
	docker compose up -d db
	docker compose exec db /usr/local/bin/wait-for-db
	$(MAKE) runmigrations
	mkdir -p .state && touch .state/db-migrated

initdb: .state/docker-build-base .state/db-populated ## Initialize and populate the database
	$(MAKE) reindex

inittuf: .state/db-migrated ## Bootstrap the TUF repository
	docker compose up -d rstuf-api
	docker compose up -d rstuf-worker
	docker compose run --rm web python -m warehouse tuf bootstrap dev/rstuf/bootstrap.json --api-server http://rstuf-api

runmigrations: .state/docker-build-base ## Run database migrations
	docker compose run --rm web python -m warehouse db upgrade head

checkdb: .state/docker-build-base ## Check database consistency
	docker compose run --rm web bin/db-check

reindex: .state/docker-build-base ## Rebuild the search index
	docker compose run --rm web python -m warehouse search reindex

dbshell: .state/docker-build-base ## Open a PostgreSQL shell
	docker compose run --rm web psql -h db -d warehouse -U postgres

##@ Cleanup

clean: ## Remove generated project files
	rm -rf dev/*.sql
	rm -rf docs/blog-site/ docs/dev-site/ docs/user-site/
	rm -rf warehouse/static/dist/ warehouse/admin/static/dist/

purge: stop clean ## Remove generated files, containers, and volumes
	rm -rf .state .coverage* .cache .state/db-populated .state/db-migrated
	docker compose down -v --remove-orphans
	docker compose rm --force

stop: ## Stop development containers
	docker compose stop

# ============================================================================
# CodeQL static analysis (runs on host, not in Docker)
# ============================================================================
# First-time run:
#   make codeql                       # install packs, build DB, analyze everything
#
# Other useful targets:
#   make codeql-analyze-python        # analyze one language against existing DB
#   make codeql-db                    # (re)build just the database
#   make codeql-rebuild               # force DB rebuild (packs/CLI sentinels kept)
#   make codeql-test                  # run custom query unit tests
#   make codeql-clean                 # remove DB, results, and sentinels
#
# The DB is automatically rebuilt when any tracked source file under
# warehouse/ changes (detected at make-invocation time via `find`).
#
# Override CODEQL_LANGS to scope to a subset (requires codeql-clean first if
# the existing DB was built with a different set):
#   make codeql CODEQL_LANGS=python
#
# Artifacts land under dev/codeql/ (gitignored):
#   dev/codeql/db/        database cluster
#   dev/codeql/results/   <language>.sarif per analyzed language

CODEQL_LANGS ?= python javascript

_codeql_db        := dev/codeql/db
_codeql_results   := dev/codeql/results

_codeql_pack_python      = .github/codeql/custom-queries/python
_codeql_custom_python    = .github/codeql/custom-queries/python/warehouse-suite.qls
_codeql_sources          := $(shell git ls-files 'warehouse/*.py' 'warehouse/*.js' ':!warehouse/migrations/*' 2>/dev/null)

.state/codeql-cli:
	@command -v codeql >/dev/null 2>&1 || { \
		echo "error: 'codeql' not found on PATH."; \
		echo "       macOS:   brew install --cask codeql"; \
		echo "       other:   https://github.com/github/codeql-cli-binaries/releases"; \
		exit 1; \
	}
	@mkdir -p .state && touch .state/codeql-cli

.state/codeql-packs: .state/codeql-cli
	codeql pack install $(_codeql_pack_python)
	@mkdir -p .state && touch .state/codeql-packs

.state/codeql-db: .state/codeql-packs .github/codeql/codeql-config.yml $(_codeql_sources)
	rm -rf $(_codeql_db)
	@mkdir -p $(dir $(_codeql_db))
	codeql database create $(_codeql_db) --db-cluster --threads=0 \
		$(addprefix --language=,$(CODEQL_LANGS)) \
		--codescanning-config=.github/codeql/codeql-config.yml
	@mkdir -p .state && touch .state/codeql-db

##@ CodeQL

codeql-db: .state/codeql-db ## Build the CodeQL database

codeql-rebuild: ## Force a CodeQL database rebuild
	rm -rf $(_codeql_db) .state/codeql-db
	$(MAKE) codeql-db

codeql-analyze-%: .state/codeql-db
	@mkdir -p $(_codeql_results)
	codeql database analyze $(_codeql_db)/$* --threads=0 \
		--format=sarif-latest \
		--output=$(_codeql_results)/$*.sarif \
		$(_codeql_custom_$*)

codeql-analyze: $(addprefix codeql-analyze-,$(CODEQL_LANGS)) ## Analyze the existing CodeQL database

codeql: codeql-analyze ## Build the CodeQL database and run analysis

codeql-test: .state/codeql-packs ## Run custom CodeQL query tests
	codeql test run $(_codeql_pack_python)/tests

codeql-clean: ## Remove CodeQL-generated files
	rm -rf dev/codeql .state/codeql-db .state/codeql-packs .state/codeql-cli

.PHONY: help build serve resetdb initdb shell dbshell tests dev-docs user-docs deps deps_upgrade_all deps_upgrade_project clean purge debug stop compile-pot runmigrations checkdb codeql codeql-db codeql-rebuild codeql-analyze codeql-test codeql-clean patch
