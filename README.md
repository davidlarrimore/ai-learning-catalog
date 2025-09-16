# Training Processing

A dockerised FastAPI + Celery backend with a lightweight single page interface for curating training courses. The backend exposes APIs to list, add, and update course metadata stored in JSON, while a Redis-backed Celery worker performs the write operations. A static SPA (served by Nginx) provides a simple UI on top of the API.

## Stack
- **Backend**: FastAPI (`backend/app/main.py`) served by Uvicorn
- **Worker**: Celery worker sharing the backend codebase
- **Broker/Result Store**: Redis 7
- **Frontend**: Static HTML/CSS/JS served by Nginx with `/api` proxied to the backend
- **Course storage**: JSON file at `data/courses.json`

## Prerequisites
- Docker and Docker Compose
## Getting Started
```bash
docker compose up --build
```
This will start four services:
- `backend` – FastAPI on [http://localhost:8000](http://localhost:8000)
- `worker` – Celery worker consuming course tasks
- `frontend` – SPA on [http://localhost:8080](http://localhost:8080)
- `redis` – Redis broker/result store on port `6379`

The FastAPI server runs with autoreload and your local repo is bind-mounted into the container so code changes take effect immediately.

### Frontend
Open [http://localhost:8080](http://localhost:8080) to:
- View the current course catalogue
- Add a new course (submits a Celery task, auto-refreshes on completion)
- Edit an existing course (loads values into the form and performs a PUT)
- Enrich from a course URL (calls `/courses/enrich` and saves the result)

### API Quick Reference
- `GET /courses` → List all stored courses
- `POST /courses` → Create a course (`CourseCreate` payload)
- `PUT /courses/{course_link}` → Update the course identified by its link
- `POST /courses/enrich` → Provide a URL (and optional provider/name) to auto-enrich and persist a course via OpenAI
- `GET /health` → Basic health check

All endpoints accept/emit JSON using the snake_case field names from `course_model.Course`.

### Environment Variables
Most settings default to sensible values but can be overridden in `docker-compose.yml` or a `.env` file:
- `COURSES_PATH` – JSON file used to persist courses (default `data/courses.json`)
- `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` – Redis connection strings
- `TASK_TIMEOUT` – seconds to wait for Celery task results (default `10`)
- `OPENAI_API_KEY` – required for `/courses/enrich`
- `OPENAI_MODEL` – model used for enrichment (default `gpt-4o-mini`)
- `OPENAI_REQUEST_TIMEOUT` – seconds to wait when fetching pages / calling OpenAI (default `60`)
- `OPENAI_CONTEXT_CHARS` – maximum characters from a fetched course page used in prompts (default `6000`)

## Project Structure (new pieces)
```
backend/
  app/
    main.py        # FastAPI application
    tasks.py       # Celery tasks for course mutations
    repository.py  # JSON-backed course persistence helper
    config.py      # Environment-driven settings
frontend/
  Dockerfile
  index.html       # Simple SPA
  app.js           # Frontend logic (fetch, forms)
  styles.css
  nginx.conf       # Static hosting + /api proxy
```

## Helper Scripts
- `./scripts/up.sh [additional docker compose args]` – default `up --detach --build`
- `./scripts/down.sh [args]` – wraps `docker compose down`
- `./scripts/restart.sh [args]` – runs `down` then `up --detach` with optional extra flags
- `./scripts/logs.sh [service...]` – tails compose logs (defaults to `-f` all services)

## Useful Commands
- `docker compose logs -f backend` – follow API logs
- `docker compose logs -f worker` – inspect the Celery worker
- `docker compose down` – stop all services

Feel free to adapt the containers (e.g. add Flower for task monitoring or hook up a persistent database) as your workflow evolves.
