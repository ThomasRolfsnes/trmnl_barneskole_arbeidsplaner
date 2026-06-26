# trmnl_barneskole_arbeidsplaner

Show a Norwegian primary school's weekly plan (*arbeidsplan*) on a
[TRMNL](https://usetrmnl.com) e-ink display.

The school publishes a fresh PDF each week behind a link that changes every time,
so this project scrapes the school page, finds the current PDF for the chosen
grade (*trinn*), renders it to a grayscale image sized for the device, and serves
it via GitHub Pages. A small TRMNL plugin polls that image and shows it
full-screen. You pick the **school** and **trinn** in the plugin settings.

Currently configured for **Minde skole** (Bergen kommune), trinn 1–7, and built
to add more schools easily.

## How it works

```
GitHub Actions (daily cron)
  └─ uv run scraper/build.py
       1. scrape each school page, map "N. trinn" → this week's PDF link
       2. download the PDF (only when the weekly link changed)
       3. render page 1 → grayscale PNG at the device resolution
       4. write docs/<school>/trinn-N.png + trinn-N.json
  └─ commit docs/ back to the repo
        │
GitHub Pages (serves docs/)
  https://thomasrolfsnes.github.io/trmnl_barneskole_arbeidsplaner/<school>/trinn-N.png
        │
TRMNL plugin (polling)
  polls …/trinn-N.json → renders <img src="{{ image_url }}"> full-screen
```

No always-on server: the rendering runs in the cron job, and the request path
only serves a static PNG. Everything fits GitHub's free tier (public repo →
unlimited Actions minutes + Pages).

The rendered files only change when the school publishes a new plan: the image
URL carries a content hash, so the committed JSON (and therefore the device
screen) stays stable until the weekly PDF actually changes.

## Repository layout

```
schools/                 one YAML per school (scraping config)
  minde.yml
scraper/                 the cron job
  build.py               orchestrates scrape → render → write docs/
  scrape.py              find the current PDF per trinn
  render.py              PDF → grayscale PNG (pypdfium2 + Pillow)
  devices.py             TRMNL device pixel profiles
  school_config.py       load schools/*.yml
docs/                    GitHub Pages root (generated images live here)
plugin/                  the TRMNL plugin (trmnlp-compatible)
  src/settings.yml       strategy, polling URL, form fields
  src/full.liquid        full-screen image
  src/half_*.liquid      mashup summaries
  src/quadrant.liquid
.github/workflows/build.yml   daily cron
pyproject.toml           dependencies (managed with uv)
```

## Setup

### 1. Enable GitHub Pages
Repo **Settings → Pages → Build and deployment → Deploy from a branch**, then
choose branch **main**, folder **/docs**, Save. The site will be at
`https://thomasrolfsnes.github.io/trmnl_barneskole_arbeidsplaner/`.

### 2. Run the cron once
Push to `main` (or **Actions → Build arbeidsplan images → Run workflow**). The
job renders all grades and commits `docs/<school>/…`. The Pages base URL is
derived automatically from the repo; override it with a repo variable
`PAGES_BASE_URL` only if you use a custom domain.

The workflow needs write access to push the generated images: repo
**Settings → Actions → General → Workflow permissions → Read and write**.

### 3. Create the TRMNL plugin
You need TRMNL Developer edition (one-time unlock). Then either:

- **Web UI:** Plugins → add a **Private Plugin** (Polling). Copy the values from
  `plugin/src/settings.yml` and paste each `*.liquid` into the matching markup
  tab. Enable **Remove bleed margin**.
- **Local (recommended):** use [`trmnlp`](https://github.com/usetrmnl/trmnlp):
  ```sh
  cd plugin
  trmnlp serve            # live preview at http://localhost:4567
  trmnlp push             # upload settings + markup (needs $TRMNL_API_KEY and an id in settings.yml)
  ```

### 4. Configure on the device
Add the plugin to a playlist, open its settings, pick **Skole** and **Trinn**.
The weekly plan is **A4 landscape**, so set the device orientation to
**landscape** for the best fit.

## Local development

```sh
# render everything to docs/ using a local base URL
uv run scraper/build.py --base-url http://localhost:8000

# limit to one school / preview without writing
uv run scraper/build.py --school minde --dry-run

# serve the output and preview the plugin against it
(cd docs && python -m http.server 8000) &
cd plugin && trmnlp serve
```

`--device` selects the render profile (`trmnl_x_landscape` default,
`trmnl_x_portrait`, `trmnl_og`).

## Adding another school

Most Bergen kommune school pages use the same "heading then download link"
layout, so adding a school is usually just a new `schools/<id>.yml`:

```yaml
id: myskole
name: Min skole
base_url: https://www.bergen.kommune.no
pages:
  - url: /omkommunen/avdelinger/min-skole/arbeidsplaner/...
    trinn: [1, 2, 3, 4]
link:
  heading_pattern: '^\s*{trinn}\.\s*trinn'   # {trinn} is substituted per grade
  href_pattern: '/api/rest/filer/'           # the PDF download link
render:
  page: 1
```

Then add the school to the `Skole` dropdown in `plugin/src/settings.yml`.
If a school's page is structured differently, adjust the regex patterns (or
extend `scraper/scrape.py` with a per-school strategy).

## Notes

- **Public data, public repo.** The plans are already published openly on the
  schools' own websites; this just reformats them. `docs/robots.txt` and a
  `noindex` tag ask search engines not to index the mirror.
- **Page selection.** Only page 1 is rendered by default (the weekly plan grid).
  Some PDFs have extra pages (info letters etc.); set `render.page` per school to
  pick a different one.
- **Be polite.** The cron runs once a day and skips downloads when the weekly
  link is unchanged.
