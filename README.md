# AI Training List

This repository curates a public, continuously updated list of AI and GenAI training opportunities. A static site publishes the catalog, while an automated backend gathers, normalizes, and enriches course metadata so people can quickly discover relevant learning paths.

## Access the Catalog
- Visit the live list at https://davidlarrimore.github.io/ai-training-list/
- The site (contents under `docs/`) loads `docs/data/courses.json` and lets you search, filter, and deep-link directly to providers.
- Updates land automatically whenever the course data is refreshed in `data/courses.json` (see automation details below).

## Request a New Course
1. Go to the repository’s **Issues** tab and choose **New issue**.
2. Select the **Request a new AI training** template ( `.github/ISSUE_TEMPLATE/new-course.yml` ).
3. Provide the course link plus any details you already know—provider name, delivery format, estimated effort, and evidence of completion are especially helpful.
4. Submit the issue. The maintainers use the supplied link to trigger an enrichment run; once approved, the new course will appear on the public list after the next sync.

## How the Automation Works
- **Source of truth:** `data/courses.json` stores each course as structured JSON. A GitHub Action (`.github/workflows/sync-courses.yml`) mirrors that file to `docs/data/courses.json` so GitHub Pages stays up to date without manual commits.
- **FastAPI API:** `backend/app/main.py` exposes `/courses` endpoints to list, add, update, and enrich training metadata. It relies on a Celery worker (`backend/app/tasks.py`) to persist writes without blocking the API.
- **Course repository:** `backend/app/repository.py` validates and saves courses, keeping the JSON store consistent and deduplicated by course link.
- **GenAI enrichment:** When a course is added or a maintainer requests `/courses/enrich`, the Celery worker calls `CourseEnricher` (`backend/app/enrichment.py`). The enricher downloads the course page, trims the raw text, and asks OpenAI to synthesize missing details (summary, track, hands-on components, skill level, difficulty, length, and completion evidence). Fields the model cannot confirm are explicitly marked `Unknown` so reviewers know what still needs verification.
- **Graceful fallbacks:** If Celery or OpenAI are unavailable, the API falls back to synchronous processing so maintainers can continue editing data locally.

## Run the Backend Locally (Optional)
Use Docker Compose to spin up the API, worker, Redis broker, and a lightweight admin SPA:

```bash
docker compose up --build
```

- Backend API: http://localhost:8000
- Frontend admin SPA: http://localhost:8080 (talks to the API for local edits)
- GitHub Pages preview: http://localhost:3000 (served by the `github-pages` Nginx container using `nginx-github-pages.conf` so it mirrors production routing and caching)
- Set `OPENAI_API_KEY` in `.env` to enable enrichment; additional tunables live in `backend/app/config.py`.

Previewing only the static site? Run `docker compose up github-pages` to launch just the local GitHub Pages mirror while you edit the files in `docs/`.

## Repository Highlights
- `backend/` – FastAPI service, Celery tasks, and OpenAI enrichment logic.
- `data/courses.json` – Canonical course catalog that powers both the API and the public site.
- `docs/` – GitHub Pages site (`index.html`, `app.js`, `data/courses.json`) deployed at the link above.
- `nginx-github-pages.conf` – Local Nginx config the Docker preview uses to emulate the GitHub Pages environment.
- `scripts/` – Convenience wrappers for Docker Compose workflows.
