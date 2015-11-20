default:
	@echo "Must call a specific subcommand"
	@exit 1

.state/env/pyvenv.cfg: requirements/dev.txt requirements/docs.txt requirements/lint.txt
	# Create our Python 3.5 virtual environment
	rm -rf .state/env
	python3.5 -m venv .state/env

	# install/upgrade general requirements
	.state/env/bin/python -m pip install --upgrade pip setuptools wheel

	# install various types of requirements
	.state/env/bin/python -m pip install -r requirements/dev.txt
	.state/env/bin/python -m pip install -r requirements/docs.txt
	.state/env/bin/python -m pip install -r requirements/lint.txt

requirements/main.txt: .state/env/pyvenv.cfg requirements/main.in
	.state/env/bin/pip-compile requirements/main.in > requirements/main.txt

	echo "" >> requirements/main.txt
	echo "# Add additional search locations" >> requirements.txt
	echo "-f https://github.com/benoitc/gunicorn/archive/master.zip#egg=gunicorn-19.4.dev" >> requirements/main.txt

.state/docker-build: Dockerfile requirements/main.txt
	# Build our docker containers for this project.
	docker-compose build

	# Mark the state so we don't rebuild this needlessly.
	mkdir -p .state
	touch .state/docker-build

build:
	docker-compose build

	# Mark this state so that the other target will known it's recently been
	# rebuilt.
	mkdir -p .state
	touch .state/docker-build

serve: .state/docker-build
	docker-compose up

tests:
	docker-compose run web env -i bin/tests --dbfixtures-config tests/dbfixtures.conf $(TESTARGS)

lint: .state/env/pyvenv.cfg
	.state/env/bin/flake8 .
	.state/env/bin/doc8 --allow-long-titles README.rst CONTRIBUTING.rst docs/ --ignore-path docs/_build/


docs: .state/env/pyvenv.cfg
	$(MAKE) -C docs/ doctest SPHINXOPTS="-W" SPHINXBUILD="$(PWD)/.state/env/bin/sphinx-build"
	$(MAKE) -C docs/ html SPHINXOPTS="-W" SPHINXBUILD="$(PWD)/.state/env/bin/sphinx-build"

initdb:
	docker-compose run web psql -h db -d postgres -U postgres -c "CREATE DATABASE warehouse ENCODING 'UTF8'"
	xz -d -k dev/example.sql.xz
	docker-compose run web psql -h db -d warehouse -U postgres -v ON_ERROR_STOP=1 -1 -f dev/example.sql
	rm dev/example.sql
	docker-compose run web python -m warehouse db upgrade head

shell:
	docker-compose run web python -m warehouse shell

.PHONY: default build serve initdb shell tests docs
