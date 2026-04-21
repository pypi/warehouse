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

default: help

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
		END { printf "\n" }' $(MAKEFILE_LIST)

##@ Build

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

build: ## Build Docker containers
	@$(MAKE) .state/docker-build
	docker system prune -f --filter "label=com.docker.compose.project=warehouse"

##@ Run

serve: .state/docker-build ## Start development server
	$(MAKE) .state/db-populated
	$(MAKE) .state/search-indexed
	docker compose up --remove-orphans

debug: .state/docker-build-base ## Run web container with debugger support
	docker compose run --rm --service-ports web

##@ Testing

tests: .state/docker-build-base ## Run test suite
	docker compose run --rm --env COVERAGE=$(COVERAGE) --env COVERAGE_CORE=$(COVERAGE_CORE) tests bin/tests --postgresql-host db $(T) $(TESTARGS)

static_tests: .state/docker-build-static ## Run frontend JavaScript tests
	docker compose run --rm static bin/static_tests $(T) $(TESTARGS)

static_pipeline: .state/docker-build-static ## Run static asset pipeline
	docker compose run --rm static bin/static_pipeline $(T) $(TESTARGS)

##@ Code Quality

reformat: .state/docker-build-base ## Format Python code
	docker compose run --rm base bin/reformat

lint: .state/docker-build-base .state/docker-build-static ## Run linters
	docker compose run --rm base bin/lint
	docker compose run --rm static bin/static_lint

##@ Documentation

dev-docs: .state/docker-build-docs ## Build and serve developer docs
	docker compose run --rm dev-docs bin/dev-docs

user-docs: .state/docker-build-docs ## Build and serve user docs
	docker compose run --rm user-docs bin/user-docs

blog: .state/docker-build-docs ## Build blog
	docker compose run --rm blog mkdocs build -f docs/mkdocs-blog.yml

##@ Dependencies

licenses: .state/docker-build-base ## Check dependency licenses
	docker compose run --rm base bin/licenses

deps: .state/docker-build-base ## Compile dependencies
	docker compose run --rm base bin/deps

deps_upgrade_all: .state/docker-build-base ## Upgrade all dependencies
	docker compose run --rm base bin/deps-upgrade -a

deps_upgrade_project: .state/docker-build-base ## Upgrade specific package (P=package)
	docker compose run --rm base bin/deps-upgrade -p $(P)

translations: .state/docker-build-base ## Update translations
	docker compose run --rm base bin/translations

requirements/%.txt: requirements/%.in
	docker compose run --rm base pip-compile --generate-hashes --output-file=$@ $<

##@ Database

resetdb: .state/docker-build-base ## Reset database to clean state
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

initdb: .state/docker-build-base .state/db-populated ## Initialize database with sample data
	$(MAKE) reindex

inittuf: .state/db-migrated ## Initialize TUF (The Update Framework)
	docker compose up -d rstuf-api
	docker compose up -d rstuf-worker
	docker compose run --rm web python -m warehouse tuf bootstrap dev/rstuf/bootstrap.json --api-server http://rstuf-api

runmigrations: .state/docker-build-base ## Run database migrations
	docker compose run --rm web python -m warehouse db upgrade head

checkdb: .state/docker-build-base ## Check database migrations
	docker compose run --rm web bin/db-check

reindex: .state/docker-build-base ## Reindex OpenSearch
	docker compose run --rm web python -m warehouse search reindex

shell: .state/docker-build-base ## Open Python shell with app context
	docker compose run --rm web python -m warehouse shell

totp: .state/docker-build-base ## Generate TOTP code for dev user
	@docker compose run --rm base bin/devtotp

dbshell: .state/docker-build-base ## Open PostgreSQL shell
	docker compose run --rm web psql -h db -d warehouse -U postgres

##@ Cleanup

clean: ## Remove generated SQL files
	rm -rf dev/*.sql

purge: stop clean ## Stop containers and remove all state
	rm -rf .state dev/.coverage* dev/.mypy_cache dev/.pip-cache dev/.pip-tools-cache dev/.pytest_cache .state/db-populated .state/db-migrated
	docker compose down -v --remove-orphans
	docker compose rm --force

stop: ## Stop all containers
	docker compose stop

.PHONY: default build serve resetdb initdb shell dbshell tests dev-docs user-docs deps deps_upgrade_all deps_upgrade_project clean purge debug stop compile-pot runmigrations checkdb

##@ Tilt

.PHONY: tilt-check
tilt-check:
	@command -v tilt >/dev/null 2>&1 || { echo "Error: tilt is not installed. Install from https://tilt.dev"; exit 1; }
	@command -v kubectl >/dev/null 2>&1 || { echo "Error: kubectl is not installed"; exit 1; }

.PHONY: tilt
tilt: tilt-check ## Start Tilt dev environment (infrastructure only)
	@printf "\n\033[1mWarehouse Tilt Development\033[0m\n"
	@printf "==========================\n\n"
	@printf "URLs (after startup):\n"
	@printf "  Tilt UI:    http://localhost:10352\n"
	@printf "  Cabotage:   http://cabotage.192-168-139-2.nip.io\n"
	@printf "  Warehouse:  http://warehouse-dev.orb.local (after Cabotage deploy)\n"
	@printf "  Maildev:    http://mail.warehouse-dev.orb.local\n"
	@printf "\n"
	tilt up --port 10352

.PHONY: tilt-down
tilt-down: ## Stop Tilt dev environment
	tilt down

.PHONY: tilt-status
tilt-status: ## Show Tilt status
	tilt get --host localhost:10352

.PHONY: tilt-logs
tilt-logs: ## Follow all Tilt logs
	tilt logs -f --host localhost:10352

.PHONY: tilt-bootstrap
tilt-bootstrap: ## Bootstrap Warehouse in Cabotage (creates org/project/apps)
	@printf "Bootstrapping Warehouse in Cabotage...\n"
	cat scripts/bootstrap_cabotage.py | kubectl exec -i -n cabotage-dev deploy/cabotage-app -- \
		sh -c "cd /opt/cabotage-app/src && python3"
	@printf "\n\033[1;32mBootstrap complete!\033[0m\n"
	@printf "Visit: http://cabotage.192-168-139-2.nip.io/organizations/warehouse\n"
