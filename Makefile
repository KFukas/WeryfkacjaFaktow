# Skróty dla Linux/macOS (Windows: scripts\*.ps1).
.PHONY: setup start test lint redteam redteam-mock docker docker-redteam e2e

setup:            ## venv, zależności, .env, baza, frontend
	scripts/setup.sh
start:            ## API :8000 + panel :5173
	scripts/start.sh
test:             ## lint + wszystkie testy offline
	scripts/test.sh
lint:
	.venv/bin/ruff check .
redteam:          ## eval red-team, model „łatwowierny” (najgorszy przypadek)
	.venv/bin/python -m redteam.eval_agent --llm gullible
redteam-mock:
	.venv/bin/python -m redteam.eval_agent --llm mock
docker:           ## cały stos w Dockerze (UI :8080, API :8000)
	docker compose up --build
docker-redteam:
	docker compose --profile redteam up --build
e2e:              ## test UI w przeglądarce (wymaga uruchomionego start + pip install -e ".[e2e]")
	.venv/bin/python scripts/ui_e2e.py
