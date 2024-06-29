DB := example
IPYTHON := no

# set environment variable WAREHOUSE_IPYTHON_SHELL=1 if IPython
# needed in development environment
ifeq ($(WAREHOUSE_IPYTHON_SHELL), 1)
    IPYTHON = yes
endif

default:
	@echo "Call a specific subcommand:"
	@echo
	@$(MAKE) -pRrq -f $(lastword $(MAKEFILE_LIST)) : 2>/dev/null\
	| awk -v RS= -F: '/^# File/,/^# Finished Make data base/ {if ($$1 !~ "^[#.]") {print $$1}}'\
	| sort\
	| egrep -v -e '^[^[:alnum:]]' -e '^$@$$'
	@echo
	@exit 1

.state/docker-build-base: Dockerfile package.json package-lock.json requirements/main.txt requirements/deploy.txt requirements/lint.txt requirements/tests.txt requirements/dev.txt
	# Build our base container for this project.
	docker compose build --build-arg IPYTHON=$(IPYTHON) --force-rm base

	# Mark the state so we don't rebuild this needlessly.
	mkdir -p .state
	touch .state/docker-build-base

.state/docker-build-static: Dockerfile package.json package-lock.json .babelrc
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

build:
	@$(MAKE) .state/docker-build

	docker system prune -f --filter "label=com.docker.compose.project=warehouse"

serve: .state/docker-build
	$(MAKE) .state/db-populated
	$(MAKE) .state/search-indexed
	docker compose up --remove-orphans

debug: .state/docker-build-base
	docker compose run --rm --service-ports web

tests: .state/docker-build-base
	docker compose run --rm tests bin/tests --postgresql-host db $(T) $(TESTARGS)

static_tests: .state/docker-build-static
	docker compose run --rm static bin/static_tests $(T) $(TESTARGS)

static_pipeline: .state/docker-build-static
	docker compose run --rm static bin/static_pipeline $(T) $(TESTARGS)

reformat: .state/docker-build-base
	docker compose run --rm base bin/reformat

lint: .state/docker-build-base .state/docker-build-static
	docker compose run --rm base bin/lint
	docker compose run --rm static bin/static_lint

dev-docs: .state/docker-build-docs
	docker compose run --rm dev-docs bin/dev-docs

user-docs: .state/docker-build-docs
	docker compose run --rm user-docs bin/user-docs

blog: .state/docker-build-docs
	docker compose run --rm blog mkdocs build -f docs/mkdocs-blog.yml

licenses: .state/docker-build-base
	docker compose run --rm base bin/licenses

deps: .state/docker-build-base
	docker compose run --rm base bin/deps

translations: .state/docker-build-base
	docker compose run --rm base bin/translations

requirements/%.txt: requirements/%.in
	docker compose run --rm base bin/pip-compile --generate-hashes --output-file=$@ $<

resetdb: .state/docker-build-base
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
	mkdir -p .state && touch .state/db-populated

.state/db-migrated: .state/docker-build-base
	docker compose up -d db
	docker compose exec db /usr/local/bin/wait-for-db
	$(MAKE) runmigrations
	mkdir -p .state && touch .state/db-migrated

initdb: .state/docker-build-base .state/db-populated
	$(MAKE) reindex

inittuf: .state/db-migrated
	docker compose up -d rstuf-api
	docker compose up -d rstuf-worker
	docker compose run --rm web python -m warehouse tuf bootstrap dev/rstuf/bootstrap.json --api-server http://rstuf-api

runmigrations: .state/docker-build-base
	docker compose run --rm web python -m warehouse db upgrade head

reindex: .state/docker-build-base
	docker compose run --rm web python -m warehouse search reindex

shell: .state/docker-build-base
	docker compose run --rm web python -m warehouse shell

dbshell: .state/docker-build-base
	docker compose run --rm web psql -h db -d warehouse -U postgres

clean:
	rm -rf dev/*.sql

purge: stop clean
	rm -rf .state dev/.coverage* dev/.mypy_cache dev/.pip-cache dev/.pip-tools-cache dev/.pytest_cache .state/db-populated .state/db-migrated
	docker compose down -v --remove-orphans
	docker compose rm --force

stop:
	docker compose stop

.PHONY: default build serve resetdb initdb shell dbshell tests dev-docs user-docs deps clean purge debug stop compile-pot runmigrations
