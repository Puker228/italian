.PHONY: format run up down migrate seed test

format:
	uv run ruff check --fix
	uv run ruff format

run:
	uv run python manage.py runserver

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	uv run python manage.py migrate

seed:
	uv run python manage.py seed_demo

test:
	uv run python manage.py test school
