## Xiaohongshu AI Agent (LangGraph + Playwright + SD + Postgres)

End-to-end agent system that automatically:

- Generates topics
- Writes Xiaohongshu-style posts
- Generates images with Stable Diffusion
- Publishes posts via Playwright automation
- Collects metrics
- Fetches/analyzes comments
- Optimizes future content strategy

### Quickstart

#### 1) Create environment

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

//Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### 2) Start PostgreSQL

```bash
docker compose up -d
```

#### 3) Configure environment variables

Copy `.env.example` to `.env` and edit:

- `DATABASE_URL`
- `XHS_BASE_URL`
- `XHS_STORAGE_STATE_PATH` (Playwright logged-in state)
- `SD_MODEL_ID` (Diffusers pipeline id)

#### 4) Create Playwright storage state (login once)

Install the browser first:

```powershell
.\scripts\install_playwright.ps1
```

1. Run:

```bash
python -m app.cli.login
```

2. A browser opens. Log into Xiaohongshu manually.
3. When you close the browser, the script saves `storage_state.json` to `XHS_STORAGE_STATE_PATH`.

#### 5) Run the agent loop

Generate a batch (topics → posts → images → publish → metrics → comments → strategy update):

```bash
python -m app.cli.run --batch-size 3
```

### Notes

- **Publishing**: this project uses browser automation. Selectors and flows may need small adjustments depending on UI changes and region.
- **Stable Diffusion**: runs locally via Diffusers by default. You can swap in a remote image API by editing `app/services/image_generator.py`.
- **Safety**: do not hardcode credentials. Prefer Playwright `storage_state.json`.

### Project layout

- `app/config/`: settings and env loading
- `app/database/`: SQLAlchemy engine, models, repositories
- `app/services/`: integrations (LLM/topic/post, SD image generation, Playwright publish, metrics/comments)
- `app/workflows/`: LangGraph graphs
- `app/cli/`: command-line entrypoints

