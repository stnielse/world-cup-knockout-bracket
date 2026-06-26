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
# The .DEFAULT rule below swallows the extra goal so Make doesn't try to
# build a target named after it.
test:
	@./scripts/run_tests.sh $(filter-out $@,$(MAKECMDGOALS))

.DEFAULT:
	@:

lint:
	$(PYTHON) -m flake8 $(SOURCES)

format:
	$(PYTHON) -m black $(SOURCES)

check:
	$(PYTHON) manage.py check
