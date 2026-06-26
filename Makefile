PYTHON := .venv/bin/python
PIP := .venv/bin/pip
SOURCES := apps config manage.py

.PHONY: install run migrate makemigrations shell createsuperuser test lint format check

install:
	$(PIP) install -r requirements.txt

run:
	$(PYTHON) manage.py runserver

migrate:
	$(PYTHON) manage.py migrate

makemigrations:
	$(PYTHON) manage.py makemigrations

shell:
	$(PYTHON) manage.py shell

createsuperuser:
	$(PYTHON) manage.py createsuperuser

# `make test [<app>[:<file>[:<test_name>]]]` — see scripts/run_tests.sh.
# The .DEFAULT rule no-ops trailing positional args *only when `test` is the
# first goal*. Any other unknown target falls through to Make's normal
# "No rule to make target" error. (Using .DEFAULT instead of `$(EXTRA):`
# style rules because the latter chokes on the colons in `app:file:name`.)
test:
	@./scripts/run_tests.sh $(filter-out $@,$(MAKECMDGOALS))

.DEFAULT:
	@if [ "$(firstword $(MAKECMDGOALS))" = "test" ]; then :; else \
	    echo "make: *** No rule to make target '$@'.  Stop." >&2; \
	    exit 2; \
	fi

lint:
	$(PYTHON) -m flake8 $(SOURCES)

format:
	$(PYTHON) -m black $(SOURCES)

check:
	$(PYTHON) manage.py check
