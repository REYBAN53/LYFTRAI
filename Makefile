.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down logs ps test test-backend test-frontend clean dev-backend dev-frontend

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

up: ## Build and start the stack (backend :8000, frontend :3000)
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example. Add your LLM_API_KEYS to it.")
	$(COMPOSE) up -d --build
	@echo "Frontend: http://localhost:3000  |  Backend: http://localhost:8000/health"

down: ## Stop the stack (chat history is kept in the named volume)
	$(COMPOSE) down

logs: ## Follow logs from both services
	$(COMPOSE) logs -f

ps: ## Show service status
	$(COMPOSE) ps

test: test-backend test-frontend ## Run all tests inside Docker

test-backend: ## Run backend tests in the Dockerfile's test stage
	docker build --target test -t lyftr-chat-backend-test ./backend
	docker run --rm lyftr-chat-backend-test

test-frontend: ## Run frontend tests (also executed during the image build)
	docker build --target build -t lyftr-chat-frontend-build ./frontend

clean: ## Stop the stack AND delete the SQLite volume
	$(COMPOSE) down -v

dev-backend: ## Run the backend without Docker (needs Python 3.12+)
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && uvicorn app.asgi:app --reload --port 8000

dev-frontend: ## Run the frontend without Docker (needs Node 22+)
	cd frontend && npm ci && npm run dev
