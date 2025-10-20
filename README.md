# Sora 2 Streamlit Studio
> Minimal Streamlit front-end for generating and managing Sora 2 text-to-video jobs.

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](#quickstart) [![Streamlit](https://img.shields.io/badge/built%20with-Streamlit-ff4b4b.svg)](https://streamlit.io) [![License](https://img.shields.io/badge/license-MIT-brightorange.svg)](#license) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

## Demo
Add `demo.gif` (≤10 MB) to the repository root and it will render here in previews.

## Features
- Prompt-to-video creation with model, duration, aspect presets, and optional reference image upload.
- Live status updates with polling, progress bar, and toast notifications while the OpenAI job runs.
- Inline playback plus download buttons for MP4 output and JSON metadata.
- Session-scoped job history to quickly revisit recent generations.
- Jobs dashboard with status/date filters, pagination, resume polling, download, and delete controls.

## Quickstart
### Prerequisites
- Python 3.10+ and `pip`
- (Optional) [`uv`](https://docs.astral.sh/uv/) or Conda for environment management

### Setup
```bash
git clone https://github.com/<your-org>/sora2-streamlit-studio.git
cd sora2-streamlit-studio
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration
1. Copy `.env-example` to `.env`
2. Populate required values:
   - `OPENAI_API_KEY` (required) – Sora 2 Videos API key
   - `OPENAI_BASE_URL` (optional) – defaults to `https://api.openai.com/v1`

### Run Locally
```bash
streamlit run app.py
```
Visit the shown URL. Streamlit hot-reloads on save; cancel with `Ctrl+C`.

## Usage Guide
1. **Create tab** – Enter a descriptive prompt, pick a model (`sora-2` or `sora-2-pro`), choose resolution/duration, and optionally upload a reference image. Submit to queue a video job and watch the live status widget.
2. When rendering finishes, preview the video inline, download the MP4/metadata, or follow the hosted asset link if available. Recent jobs appear in-session for quick access.
3. **Jobs tab** – Browse existing jobs with status/date filters. Use *Open* to refresh metadata, *Resume polling* for in-progress renders, *Download* to fetch the MP4, and *Delete* to remove a job from OpenAI (with confirmation). After 1 hour post generation, you can no longer download the video.

## Troubleshooting
- **Missing wheels on Apple Silicon:** upgrade pip (`pip install --upgrade pip`) and retry install.
- **`openai` SSL or quota errors:** confirm the API key is active, region allowed, and quota sufficient; inspect Streamlit logs for full tracebacks.
- **Large MP4s fail to download:** Streamlit limits payload sizes; prefer streaming from the hosted asset URL when available.
- **Compile errors:** run `python -m compileall app.py` before commits to catch syntax issues early.

## Project Structure
```text
app.py                # Streamlit entrypoint with page navigation and sidebar hints
assets/README.md      # Placeholder for logos, demo media, or prompt templates
lib/api.py            # OpenAI Videos API client wrappers and polling helpers
lib/state.py          # Session state setup, caching, and environment loading
lib/ui.py             # Reusable Streamlit UI helpers and toast utilities
pages/create.py       # Prompt composer, submission flow, and result display
pages/jobs.py         # Jobs dashboard with filtering, polling, and management
requirements.txt      # Streamlit + OpenAI dependencies
AGENTS.md             # Internal contributor guidelines for agent workflows
```

## Contributing
- Open an issue before large changes; small bug fixes are welcome via pull request.
- Use conventional commits where practical (e.g., `feat: add gallery filters`).
- Run local checks: `python -m compileall app.py` (and `pytest` once tests are added).
- Include screenshots or GIFs for UI changes in PR descriptions.

## License
License is currently unspecified. Add an MIT (or similar OSI-approved) license file before publishing the repository.

## Disclaimer
Not affiliated with OpenAI or the Sora team. Use for educational and demo purposes only; follow OpenAI usage policies and guard private API keys.
