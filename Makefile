BINDIR = $(PWD)/.state/env/bin
TRAVIS := $(shell echo "$${TRAVIS:-false}")
PR := $(shell echo "$${TRAVIS_PULL_REQUEST:-false}")
BRANCH := $(shell echo "$${TRAVIS_BRANCH:-master}")
DB := example
IPYTHON := no
RUN_IN_DOCKER =
RUN_IN_DOCKER_DEP = .state/env/pyvenv.cfg

# set environment variable WAREHOUSE_IPYTHON_SHELL=1 if IPython
# needed in development environment
ifeq ($(WAREHOUSE_IPYTHON_SHELL), 1)
    IPYTHON = yes
endif

ifeq ($(TRAVIS), false)
    RUN_IN_DOCKER = docker-compose run --rm build
    RUN_IN_DOCKER_DEP = .state/docker-build
    PYTHON = $(shell $(RUN_IN_DOCKER) which python)
    BINDIR = $(shell dirname $(PYTHON))
endif

define DEPCHECKER
import sys

from pip._internal.req import parse_requirements

left, right = sys.argv[1:3]
left_reqs = {
    d.name.lower()
	for d in parse_requirements(left, session=object())
}
right_reqs = {
    d.name.lower()
	for d in parse_requirements(right, session=object())
}

extra_in_left = left_reqs - right_reqs
extra_in_right = right_reqs - left_reqs

if extra_in_left:
	for dep in sorted(extra_in_left):
		print("- {}".format(dep))

if extra_in_right:
	for dep in sorted(extra_in_right):
		print("+ {}".format(dep))

if extra_in_left or extra_in_right:
	sys.exit(1)
endef

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
	# Create our Python 3.6 virtual environment
	rm -rf .state/env
	python3.6 -m venv .state/env

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
	docker-compose build --build-arg IPYTHON=$(IPYTHON) web
	docker-compose build worker
	docker-compose build static

	# Mark the state so we don't rebuild this needlessly.
	mkdir -p .state
	touch .state/docker-build

build:
	docker-compose build --build-arg IPYTHON=$(IPYTHON) web
	docker-compose build worker
	docker-compose build static

	# Mark this state so that the other target will known it's recently been
	# rebuilt.
	mkdir -p .state
	touch .state/docker-build

serve: .state/docker-build
	docker-compose up --remove-orphans

debug: .state/docker-build
	docker-compose run --rm --service-ports web

tests:
	docker-compose run --rm web env -i ENCODING="C.UTF-8" \
								  PATH="/opt/warehouse/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
								  bin/tests --postgresql-host db $(T) $(TESTARGS)


reformat: $(RUN_IN_DOCKER_DEP)
	$(RUN_IN_DOCKER) $(BINDIR)/black warehouse/ tests/

lint: $(RUN_IN_DOCKER_DEP)
	$(RUN_IN_DOCKER) $(BINDIR)/flake8 .
	$(RUN_IN_DOCKER) $(BINDIR)/black --check warehouse/ tests/
	$(RUN_IN_DOCKER) $(BINDIR)/doc8 --allow-long-titles README.rst CONTRIBUTING.rst docs/ --ignore-path docs/_build/
	# TODO: Figure out a solution to https://github.com/deezer/template-remover/issues/1
	#       so we can remove extra_whitespace from below.
	$(RUN_IN_DOCKER) $(BINDIR)/html_lint.py --printfilename --disable=optional_tag,names,protocol,extra_whitespace,concerns_separation `find ./warehouse/templates -path ./warehouse/templates/legacy -prune -o -name '*.html' -print`
ifneq ($(TRAVIS), false)
	# We're on Travis, so we can lint static files locally
	./node_modules/.bin/eslint 'warehouse/static/js/**' '**.js' --ignore-pattern 'warehouse/static/js/vendor/**'
	./node_modules/.bin/sass-lint --verbose
else
	# We're not on Travis, so we should lint static files inside the static container
	docker-compose run --rm static ./node_modules/.bin/eslint 'warehouse/static/js/**' '**.js' --ignore-pattern 'warehouse/static/js/vendor/**'
	docker-compose run --rm static ./node_modules/.bin/sass-lint --verbose
endif

docs: $(RUN_IN_DOCKER_DEP)
	$(MAKE) -C docs/ doctest SPHINXOPTS="-W" RUN_IN_DOCKER="$(RUN_IN_DOCKER)" SUBDIR=docs BINDIR=$(BINDIR)
	$(MAKE) -C docs/ html SPHINXOPTS="-W" RUN_IN_DOCKER="$(RUN_IN_DOCKER)" SUBDIR=docs BINDIR=$(BINDIR)

licenses:
	bin/licenses

export DEPCHECKER
deps: .state/env/pyvenv.cfg
	$(RUN_IN_DOCKER) $(eval TMPDIR := $(shell mktemp -d))
	$(RUN_IN_DOCKER) $(BINDIR)/pip-compile --no-annotate --no-header --upgrade --allow-unsafe -o $(TMPDIR)/deploy.txt requirements/deploy.in > /dev/null
	$(RUN_IN_DOCKER) $(BINDIR)/pip-compile --no-annotate --no-header --upgrade --allow-unsafe -o $(TMPDIR)/main.txt requirements/main.in > /dev/null
	$(RUN_IN_DOCKER) $(BINDIR)/pip-compile --no-annotate --no-header --upgrade --allow-unsafe -o $(TMPDIR)/lint.txt requirements/lint.in > /dev/null
	$(RUN_IN_DOCKER) python $(TMPDIR)/deploy.txt requirements/deploy.txt -c "$$DEPCHECKER"
	$(RUN_IN_DOCKER) python - $(TMPDIR)/main.txt requirements/main.txt -c "$$DEPCHECKER"
	$(RUN_IN_DOCKER) python - $(TMPDIR)/lint.txt requirements/lint.txt -c "$$DEPCHECKER"
	$(RUN_IN_DOCKER) rm -r $(TMPDIR)
	$(RUN_IN_DOCKER) $(BINDIR)/pip check

travis-deps:
ifneq ($(PR), false)
	git fetch origin $(BRANCH):refs/remotes/origin/$(BRANCH)
	git diff --name-only $(BRANCH) | grep '^requirements/' || exit 0 && $(MAKE) deps
endif

initdb:
	docker-compose run --rm web psql -h db -d postgres -U postgres -c "DROP DATABASE IF EXISTS warehouse"
	docker-compose run --rm web psql -h db -d postgres -U postgres -c "CREATE DATABASE warehouse ENCODING 'UTF8'"
	xz -d -f -k dev/$(DB).sql.xz --stdout | docker-compose run --rm web psql -h db -d warehouse -U postgres -v ON_ERROR_STOP=1 -1 -f -
	docker-compose run --rm web python -m warehouse db upgrade head
	$(MAKE) reindex

reindex:
	docker-compose run --rm web python -m warehouse search reindex

shell:
	docker-compose run --rm web python -m warehouse shell

clean:
	rm -rf warehouse/static/components
	rm -rf warehouse/static/dist
	rm -rf dev/*.sql

purge: stop clean
	rm -rf .state
	docker-compose rm --force

stop:
	docker-compose down -v

.PHONY: default build serve initdb shell tests docs deps travis-deps clean purge debug stop
