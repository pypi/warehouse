BINDIR = $(PWD)/.state/env/bin
GITHUB_BASE_REF := $(shell echo "$${GITHUB_BASE_REF:-false}")
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

.state/env/pyvenv.cfg: requirements/dev.txt requirements/docs.txt requirements/lint.txt requirements/ipython.txt
	# Create our Python 3.9 virtual environment
	rm -rf .state/env
	python3.9 -m venv .state/env

	# install/upgrade general requirements
	.state/env/bin/python -m pip install --upgrade pip setuptools wheel

	# install various types of requirements
	.state/env/bin/python -m pip install -r requirements/dev.txt
	.state/env/bin/python -m pip install -r requirements/docs.txt
	.state/env/bin/python -m pip install -r requirements/lint.txt

	# install ipython if enabled
ifeq ($(IPYTHON),"yes")
	.state/env/bin/python -m pip install -r requirements/ipython.txt
endif

.state/docker-build: Dockerfile package.json package-lock.json requirements/main.txt requirements/deploy.txt
	# Build our docker containers for this project.
	docker-compose build --build-arg IPYTHON=$(IPYTHON) --force-rm web
	docker-compose build --force-rm worker
	docker-compose build --force-rm static

	# Mark the state so we don't rebuild this needlessly.
	mkdir -p .state
	touch .state/docker-build

build:
	@$(MAKE) .state/docker-build

	docker system prune -f --filter "label=com.docker.compose.project=warehouse"

serve: .state/docker-build
	docker-compose up --remove-orphans

debug: .state/docker-build
	docker-compose run --rm --service-ports web

tests: .state/docker-build
	docker-compose run --rm web env -i ENCODING="C.UTF-8" \
								  PATH="/opt/warehouse/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
								  bin/tests --postgresql-host db $(T) $(TESTARGS)

static_tests: .state/docker-build
	docker-compose run --rm static env -i ENCODING="C.UTF-8" \
								  PATH="/opt/warehouse/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
								  bin/static_tests $(T) $(TESTARGS)

static_pipeline: .state/docker-build
	docker-compose run --rm static env -i ENCODING="C.UTF-8" \
								  PATH="/opt/warehouse/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
								  bin/static_pipeline $(T) $(TESTARGS)

reformat: .state/docker-build
	docker-compose run --rm web env -i ENCODING="C.UTF-8" \
								  PATH="/opt/warehouse/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
								  bin/reformat

lint: .state/docker-build
	docker-compose run --rm web env -i ENCODING="C.UTF-8" \
								  PATH="/opt/warehouse/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
								  bin/lint && bin/static_lint

docs: .state/docker-build
	docker-compose run --rm web env -i ENCODING="C.UTF-8" \
								  PATH="/opt/warehouse/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
								  bin/docs

licenses:
	bin/licenses

deps: .state/docker-build
	docker-compose run --rm web env -i ENCODING="C.UTF-8" \
								  PATH="/opt/warehouse/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
								  bin/deps

requirements/%.txt: requirements/%.in .state/env/pyvenv.cfg
	$(BINDIR)/pip-compile --allow-unsafe --generate-hashes --output-file=$@ $<

github-actions-deps:
ifneq ($(GITHUB_BASE_REF), false)
	git fetch origin $(GITHUB_BASE_REF):refs/remotes/origin/$(GITHUB_BASE_REF)
	# Check that the following diff will exit with 0 or 1
	git diff --name-only FETCH_HEAD || test $? -le 1 || exit 1
	# Make the dependencies if any changed files are requirements files, otherwise exit
	git diff --name-only FETCH_HEAD | grep '^requirements/' || exit 0 && bin/deps
endif

initdb:
	docker-compose run --rm web psql -h db -d postgres -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname ='warehouse';"
	docker-compose run --rm web psql -h db -d postgres -U postgres -c "DROP DATABASE IF EXISTS warehouse"
	docker-compose run --rm web psql -h db -d postgres -U postgres -c "CREATE DATABASE warehouse ENCODING 'UTF8'"
	xz -d -f -k dev/$(DB).sql.xz --stdout | docker-compose run --rm web psql -h db -d warehouse -U postgres -v ON_ERROR_STOP=1 -1 -f -
	docker-compose run --rm web python -m warehouse db upgrade head
	$(MAKE) reindex
	docker-compose run web python -m warehouse sponsors populate-db

reindex:
	docker-compose run --rm web python -m warehouse search reindex

shell:
	docker-compose run --rm web python -m warehouse shell

clean:
	rm -rf dev/*.sql

purge: stop clean
	rm -rf .state
	docker-compose rm --force

stop:
	docker-compose down -v

translations: .state/docker-build
	docker-compose run --rm web env -i ENCODING="C.UTF-8" \
								  PATH="/opt/warehouse/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
								  bin/translations



.PHONY: default build serve initdb shell tests docs deps clean purge debug stop compile-pot
