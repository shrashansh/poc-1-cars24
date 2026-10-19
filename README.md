# Cars24 Pre-Inspection AI · proof of concept

Built by Shrashansh Dixit (shrashansh.dixit@gmail.com).

**Live demo:** https://poc-1-cars24.vercel.app/

A seller photographs the car before Cars24 sends an inspector. A set of agents checks the photos with an
OpenAI vision model, reconciles the findings with the RC, and narrows a real price reference. The inspector
then arrives with a checklist instead of a blank car.

Nothing in this project is mocked. The sample car is real (the author's 2024 Tata Nexon, photographed on a
phone), every analysis is a live OpenAI call, and the only prices used are real quotes.

## Run it

You need Python 3.10+ and an OpenAI API key with access to a vision model.

**Windows:** double-click `run.bat`.
**macOS / Linux:** `./run.sh`

The first run creates a `.env` file and stops. Open `.env`, paste your key after `OPENAI_API_KEY=`, and run again.
Then open http://localhost:8000.

Manual setup, if you prefer:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
copy .env.example .env          # Windows  (cp on macOS / Linux), then add your key
python run.py
```

`OPENAI_MODEL` in `.env` sets the model (default `gpt-4.1-mini`). Any model on your account that accepts
images works; a larger model reads plates, badges and handwriting more reliably.

## Using it

1. The sample car loads by default: 7 real photos and the RC. Press **Run pre-inspection**.
2. To test your own car, tap any photo slot and choose a photo. Change the model, year, variant and km band to
   match. Empty slots are skipped.
3. Try declaring the wrong variant (for example "Creative") to see the variant check re-quote the car.

A run makes about 6 OpenAI calls and takes 20–60 seconds depending on the model.

## How it works

| Step | Agent | Engine | What it does |
|---|---|---|---|
| 1 | Capture QA | local | Resolution, darkness, glare, blur per photo |
| 2 | Identity | OpenAI | Reads the plate and colour; checks every photo is the same car; matches the RC record |
| 2 | Variant | OpenAI | Badges, wheels, cabin, seat trim and the RC classification vs the declared variant |
| 2 | Odometer | OpenAI | Reads the ODO value; flags warning lights |
| 2 | Damage | OpenAI | Visible defects by panel, non-original parts (e.g. a swapped wheel), tyre wear |
| 2 | Document | OpenAI | Reads the RC fields; reads a service record if one is provided |
| 3 | Cross-check | rules | Plate vs RC, km vs service history, rollback, km per year, hypothecation, non-original parts |
| 4 | Pricing | rules | Starts from a real price reference and narrows it for each verified fact |
| 5 | Explainer | template + OpenAI | Seller message (English, plus Hindi), seller tips, inspector checklist |

Step 2 agents run in parallel. A finding below 60% confidence is never used for pricing; it becomes an
inspector flag. If an agent fails, the others still finish and the report says what failed.

### Pricing rules

- The starting range is a **real** quote from `poc/data/price_references.json`:
  - Tata Nexon Creative+ Dark 2024: ₹7,05,000 (Cars24) to ₹7,75,000 (Spinny), real post-inspection offers for the sample car.
  - Maruti Swift VXI 2019: ₹3,61,372 to ₹3,99,545, a live cars24.com estimate at 40–50k km.
- If the photos confidently show a different variant, the car is re-quoted at that variant (when a reference exists).
- Each verified fact (variant, odometer, three or more exterior sides, regular service history) narrows the range.
  The narrowing factors in `band_rules` are tunable method parameters, to be calibrated on Cars24's
  estimate-versus-final outcomes. The range never narrows below ±3%, because engine, gearbox and flood damage
  cannot be seen in photos.
- Visible damage and non-original parts are listed for Cars24's deduction table. The POC does not invent rupee
  deductions.
- No real reference for a car means no rupee range; the findings are still reported.

## Data in this project

| File | Contents |
|---|---|
| `poc/data/samples/nexon/` | Real phone photos of the sample car. Re-saved to strip GPS and other metadata. Personal fields on the RC (owner, address, nominee, chassis and engine numbers, sale amount) are blacked out. `front_left`, `rear_right` and `dash_night` are extra shots you can swap in. |
| `poc/data/rc_registry.json` | One record built from the sample car's RC (no personal data). Stands in for a Vahan / CarInfo lookup. |
| `poc/data/price_references.json` | Real price references only, with their sources. |
| `poc/data/vehicles.json` | Model catalogue and simplified variant descriptions used in the prompts. |

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Whether the OpenAI key is set, and the model |
| GET | `/api/catalog` | Models, years, variants, km bands, photo slots |
| GET | `/api/samples` | The sample car and its photo URLs |
| POST | `/api/inspect` | Multipart form: `rc_number`, `model_id`, `year`, `declared_variant`, `km_band_index`, and per slot either `photo_<slot>` (file) or `sample_<slot>` (sample path). Returns the full report as JSON. |

Slots: `front`, `rear`, `left`, `right`, `dash`, `interior`, `seats`, `tyre`, `rc`, `service`.

## Limits

- Photos are uploaded files. The production version would use live in-app capture so photos cannot be old or borrowed.
- Vision models cannot see inside the car or measure paint thickness or tread depth; those stay with the inspector.
- The sample car has no service record or tyre close-up, so those checks are skipped for it.
- Only two cars have real price references. Cars24's pricing engine would replace `price_references.json`.

## Project layout

```
run.py                  start the server
poc/server.py           Flask routes and upload handling
poc/orchestrator.py     runs the agents and builds the report
poc/vision.py           OpenAI vision client (HTTPS, JSON mode)
poc/agents/             one module per agent
poc/data/               real sample photos, RC record, price references, catalogue
static/                 web UI (HTML, CSS, JavaScript; no build step)
```

## Deploy on Vercel

The live demo at https://poc-1-cars24.vercel.app/ is deployed this way.


1. On vercel.com choose **Add New → Project** and import this repository. Keep the detected settings; `app.py` is the entry point and `requirements.txt` is installed automatically.
2. Under **Settings → Environment Variables** add `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`), then deploy.
3. Open `/api/health` on your deployment; it should show `"openai_ready": true`.

Vercel limits a request to 4.5 MB, so the browser re-encodes uploaded photos to JPEG (1600 px, smaller if needed) before sending them. The deployed site uses your OpenAI key for every visitor; turn on Deployment Protection or set a spend limit on the key.
