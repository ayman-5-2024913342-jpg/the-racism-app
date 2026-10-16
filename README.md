# THE GREAT APP

Photo-based skin tone analysis and personal color discovery. FastAPI + Jinja2 + HTMX + vanilla JS (Cropper.js),
SQLAlchemy (SQLite locally, PostgreSQL in production), Pillow / OpenCV / scikit-image for the analysis.

This is the finished version of your **Milestone 2** project (Milestones 3-9 added on top). Your layout
(`templates/`, `static/`), visual design, env var names and Milestone 2 tests are preserved.

> **Read this first: verification status.** See [Verification status](#verification-status). The image-analysis code and
> templates were executed and tested while building this. The FastAPI server, database, browser behavior (camera, cropper,
> HTMX) and the route/security/DB test files were **written but not run**, because the build environment had no network
> access to install FastAPI/SQLAlchemy/pytest. Run `pytest` once on your machine before relying on it.

## What it does

1. **Upload or take a photo** (JPEG, PNG, WebP; drag-and-drop, file picker, camera with permission handling).
2. **Crop** with Cropper.js (zoom, pan, reset, keyboard controls, animated "how to crop" hint) and confirm.
3. **Analyze** (`POST /api/analyze`): validate -> decode in memory -> quality checks -> skin pixels -> robust CIELAB color ->
   shade band + undertone (or "inconclusive") -> reliability score -> palette.
4. **Results page** with sampled color, shade band, undertone, RGB/HEX/CIELAB/LCh/ITA, reliability breakdown, warnings,
   complementary palette, JSON export, palette PNG, save / delete / contribute controls.
5. **Saved results** (a public list of every saved result), **Settings** (defaults, withdraw contributions, delete everything) and an honest **Distribution** page.

Skin tone estimates are never presented as objective, beauty or ranking scores. The UI says so repeatedly.

## Quick start

Python 3.12+ required. Cropper.js and HTMX load from CDNs (internet needed in the browser).
Camera access needs `localhost` or HTTPS.

```bash
# Linux / macOS
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```
```powershell
# Windows PowerShell
py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 . Locally, tables are created automatically (`AUTO_CREATE_TABLES=true`).

```bash
pytest            # full suite
```

## Pages and endpoints

| Route | Purpose |
|---|---|
| `GET /`, `/analyze`, `/history`, `/settings`, `/distribution` | Pages |
| `GET /results/{id}` | Result (only for the browser that created it; others get 404) |
| `POST /api/upload`, `/api/confirm-crop` | Validate + safely re-encode a preview (nothing stored) |
| `POST /api/analyze` | Run the analysis on a confirmed crop; returns `{id, result_url, ...}` |
| `POST /results/{id}/save` `unsave` `share` `unshare`, `DELETE /results/{id}` | HTMX actions |
| `GET /results/{id}/export.json`, `/palette.png` | Exports |
| `POST /settings`, `/settings/withdraw-shared`, `/settings/delete-all` | Preferences and data controls |
| `GET /distribution/chart.png?source=synthetic\|real` | Chart (real only after enough opt-in data) |
| `GET /health` | Liveness + DB check |

Errors from `/api/*` and HTMX requests are JSON: `{"detail": "...", "code": "..."}`.

## How the estimate works (documented heuristics, not validated science)

Implemented in `app/services/skin.py` (rules are listed at the top of that file) and `quality.py`.

1. **Skin mask**: YCrCb range **and** HSV range, plus morphological clean-up. If fewer than 10% of pixels look like skin the API
   returns `needs_manual_region`; the user can confirm "treat my whole crop as skin" to bypass detection.
2. **Usable pixels**: exclude L* < 10, L* > 97 and clipped pixels (any channel >= 252).
3. **Robust color**: trim outliers by distance from the median (MAD-based), take the per-channel **median in CIELAB (D65)**.
4. **Shade band**: Individual Typology Angle `atan((L*-50)/b*)`, bands after Chardon et al. (1991). Flagged when within 3 degrees of a boundary.
5. **Undertone**: hue angle `atan2(b*, a*)`: <50 cool, 50-58 neutral, >58 warm; **inconclusive** near boundaries, at low chroma,
   under a detected color cast, or when reliability is low.
6. **Reliability** (0-1): weighted geometric mean of six measurable factors: skin coverage, sample size, color consistency,
   exposure, detail, lighting color (near-neutral pixels checked for a tint). Labeled Higher / Moderate / Low.
7. **Palette**: complement, split complements, analogous and two neutrals generated in LCh, gamut-mapped to sRGB.

**Limits (shown in the UI too):** CIELAB is only approximately perceptually uniform and assumes viewing conditions a phone photo
lacks. ITA bands come from calibrated instruments. Lighting, exposure, makeup, filters, white balance and camera processing all
change the numbers. Thresholds are reasonable starting points, not clinically validated; they are constants at the top of `skin.py`.

## Privacy model (what the server processes and keeps)

* Photos/crops are decoded **in memory** and never written to disk or the database. Logs contain no images, colors or filenames.
* Decoding drops EXIF/GPS/ICC metadata. Content is validated by decoding, not by extension or MIME type.
* Every analysis stores only computed values (color, labels, scores, palette) under an unguessable id (128-bit random).
  **Unsaved results stay private to their browser and are deleted after `RESULT_TTL_HOURS` (default 24)**.
  **Saved results are public**: anyone can view them (and the name entered) at `/results/<id>` and in the list at `/history`;
  only the browser that created a result can change or delete it. Public pages send `X-Robots-Tag: noindex`.
* No accounts. A random token in an HttpOnly cookie identifies the browser; only a keyed hash (HMAC with `APP_SECRET_KEY`) is stored.
  Clearing cookies means losing the ability to delete your saved results; that is a trade-off of having no accounts.
* **Distribution sharing is off by default.** It requires saving first, and shares only the lightness number (L*), no id, date or image.
  Real data is shown only at >= `DISTRIBUTION_MIN_N` contributions; bars with < 5 are hidden; individual records are never exposed.
  Until then, the chart is generated **synthetic** data, labeled in the page and inside the image.
* HTTPS protects data in transit; it does not by itself make a service private. Your host/proxy may still see request metadata (IP, timing).

## Security measures

* Size limits while streaming, pixel/dimension limits, decompression-bomb handling, first frame only for animations.
* CSRF: double-submit token (HttpOnly cookie + `X-CSRF-Token` header embedded by HTMX/fetch) plus Origin check on all non-GET requests.
* `TrustedHostMiddleware` (`ALLOWED_HOSTS`), security headers always; CSP + HSTS in production.
* Authorization: saved results are viewable by anyone; unsaved results only by their owner (others get a 404). Save, share and delete require ownership (delete by a non-owner returns 403).
* Rate limiting (in-memory, per process) and a cap on concurrent CPU-bound analyses; analysis runs in worker threads, off the event loop.
* Parameterised queries only (SQLAlchemy). Production refuses to start with a weak/placeholder `APP_SECRET_KEY`; `/docs` is disabled.

## Configuration

See `.env.example`. Key variables: `APP_ENV`, `APP_SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `TRUSTED_ORIGINS`, `MAX_UPLOAD_MB`,
`RESULT_TTL_HOURS`, `DISTRIBUTION_MIN_N`, `RATE_LIMIT_PER_MINUTE`, `COOKIE_SECURE`.

## Deployment (Milestone 9)

1. Create a PostgreSQL database and set `DATABASE_URL` (`postgres://` / `postgresql://` URLs are accepted).
2. Set `APP_ENV=production`, a random `APP_SECRET_KEY` (32+ chars), `ALLOWED_HOSTS=your.domain`. Put the app behind HTTPS.
3. Install `requirements-prod.txt`, run `alembic upgrade head`, then `gunicorn app.main:app -c gunicorn.conf.py`.
   (`Procfile` and `Dockerfile` do exactly this; the Docker image runs migrations on start.)
4. Behind a proxy, set `FORWARDED_ALLOW_IPS` to the proxy address; if the proxy rewrites `Host`, add your origin to `TRUSTED_ORIGINS`.
5. Production notes: the rate limiter is per process (use a shared limiter or proxy limits when scaling out); set request-size limits at the
   proxy as well; consider vendoring Cropper.js/HTMX (add SRI) rather than using CDNs; add a periodic job or rely on the built-in purge
   (expired unsaved results are purged at startup and on each analysis).

## Manual QA checklist (not yet performed)

* Phone + desktop: upload, camera (allow and deny permission), crop with touch/mouse/keyboard, analyze, save, export, delete.
* Widths 360 / 768 / 1280; keyboard-only run through every page; screen reader pass on results and chart table; zoom to 200%.
* Photos: daylight, warm indoor light, filtered, with makeup, very dark, very bright, tiny crop, non-skin crop. Confirm warnings/inconclusive behave sensibly.
* Run `lighthouse` accessibility audit on `/`, `/analyze`, `/results/<id>`.

## Verification status

**Executed during development:**
* 37 service-level tests (image validation, analysis rules, palette, distribution chart, export PNG, rate limiter) - all passing
  (run with a stand-in for pytest, since pytest was not installable there).
* All templates rendered with Jinja using real analysis output; HTML tag balance and output escaping checked.
* Static check of all Python files for undefined names and broken internal imports; Alembic migration cross-checked against the models.

**Written but NOT executed:** the FastAPI app itself, `tests/test_pages.py`, `test_analysis_api.py`, `test_security.py`,
`test_repository.py`, `test_migrations.py`, Alembic runs, PostgreSQL, and everything in a real browser. Expect to fix small issues the first time
you run `pytest`; the failures should point straight at them.

## Decisions and deviations from the original brief

* **Tailwind CSS was not introduced**: your Milestone 2 design system (`static/css/styles.css`) is kept and extended, so nothing visual was rewritten.
* **HTMX added** for save/unsave/share/delete/settings. **Cropper.js** stays on cdnjs as in Milestone 2.
* No user accounts (the brief allows this for the first release); anonymous cookie identity instead.
* The crop is uploaded as lossless PNG (<= 1200 px) so JPEG compression doesn't shift measured colors; the JPEG preview is only for display.
* HEIC/HEIF (common on iPhones when exporting) is not supported; use JPEG/PNG/WebP.
