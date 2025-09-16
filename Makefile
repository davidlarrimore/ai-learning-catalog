.PHONY: help up down restart logs github-pages test-pages clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

up: ## Start all services (backend, worker, frontend, GitHub Pages preview)
	docker compose up --build -d

down: ## Stop all services
	docker compose down

restart: ## Restart all services
	docker compose down
	docker compose up --build -d

logs: ## Follow logs from all services
	docker compose logs -f

github-pages: ## Start only GitHub Pages preview server
	docker compose up github-pages -d
	@echo ""
	@echo "🚀 GitHub Pages preview running at http://localhost:3000"
	@echo ""

test-pages: ## Quick test - start GitHub Pages preview and open in browser
	@echo "Starting GitHub Pages preview server..."
	@docker compose up github-pages -d
	@sleep 2
	@echo ""
	@echo "✅ GitHub Pages preview is running!"
	@echo "📝 View your site at: http://localhost:3000"
	@echo ""
	@echo "💡 Your github-pages/ folder is being served"
	@echo "   - Make changes to github-pages/ files and refresh your browser"
	@echo "   - No rebuild needed - changes are instant!"
	@echo ""
	@echo "To stop: make down or docker compose stop github-pages"
	@echo ""

backend-only: ## Start only backend services (API + worker + Redis)
	docker compose up backend worker redis -d

frontend-only: ## Start only frontend admin SPA
	docker compose up frontend -d

clean: ## Remove all containers, volumes, and images
	docker compose down -v --rmi all

status: ## Show status of all services
	docker compose ps
