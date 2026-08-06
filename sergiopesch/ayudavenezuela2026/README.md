---
title: AyudaVenezuela2026
emoji: 🆘
colorFrom: green
colorTo: red
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Disaster support map for Venezuela response.
---

# AyudaVenezuela2026

AyudaVenezuela2026 is a concept foundation for a Venezuela-focused successor to the disaster-response work described in Hugging Face's 2023 post, [Using ML for Disasters](https://huggingface.co/blog/using-ml-for-disasters).

This Hugging Face Space is an interactive prototype for a **public earthquake damage visualization**. It combines open Sentinel-2 Cloudless national imagery, a public Vantor pre/post satellite slider cataloged through NASA Earthdata GIS, Microsoft AI for Good / HDX affected-building damage evidence, Venezuela-wide search and affected-coverage context, an opt-in NASA/NISAR displacement overlay, trusted-source data pipeline, source health summary, daily refresh metadata, and public-safe geospatial context for the June 2026 Venezuela earthquake response.

The immediate operating context is the June 24, 2026 north-central Venezuela earthquake emergency, with severe reported impacts around La Guaira and Greater Caracas. The project point of view is:

> Build a human-validated disaster intelligence and communication platform, not an autonomous AI responder.

The system should help local NGOs, civil protection actors, health and WASH teams, community focal points, and diaspora support networks answer five practical questions:

1. What happened, where, and when?
2. Who is affected, missing, displaced, injured, or unreachable?
3. What is needed now?
4. What information is uncertain, duplicated, stale, or unsafe to publish?
5. What should be verified, routed, or communicated next?

## What This Space Demonstrates

- A map-first public damage viewer for people outside Venezuela to understand the scale and location of affected buildings.
- An open EOX Sentinel-2 Cloudless 2024 basemap for shareable Venezuela-wide optical context at 10 m resolution.
- An opt-in public satellite before/after slider using one pre-event Vantor LG02 scene from 7 Apr 2026 and one post-event Vantor LG05 scene from 27 Jun 2026, clipped to the shared source footprint, with Microsoft/HDX affected-building damage evidence kept as a separate opt-in overlay.
- A default Venezuela-wide affected-coverage overlay that distinguishes the national map/search envelope, NASA/NISAR and NASA/OSU analyzed corridors, and the verified Microsoft/HDX Catia damage footprint.
- An opt-in NASA/NISAR line-of-sight surface-displacement overlay derived from 13 Jun and 25 Jun 2026 SAR imagery at 80 m posting.
- Microsoft AI for Good Lab / HDX Catia La Mar building-damage context, delivered as transparent multi-zoom raster damage tiles for the first public map view.
- A Microsoft/HDX damage overlay that explains affected-building footprint density on top of the satellite view.
- A trusted-source pipeline that snapshots HDX, HOT/OSM, Google Research Open Buildings, Microsoft, OCHA/UNEP, HeiGIT, and USGS metadata into `/api/trusted-data`.
- A bilingual public-data feed for consolidated, redacted, or aggregate signals.
- Local deterministic triage with optional Hugging Face model support through a backend-only token.
- A single public view with no report-submission workflow and no personal-data intake in the Space.

The report-like records visible in this demo are public-data fixtures used to demonstrate filtering and visualization. This Space does not accept report submissions or personal data.

## Repository Contents

- [Point of view](docs/00-point-of-view.md): the established product stance and what changes from the Turkey earthquake project.
- [Research brief](docs/01-research-brief.md): current crisis context, affected areas, constraints, and needs.
- [Product strategy](docs/02-product-strategy.md): proposed platform modules, architecture, roadmap, and evaluation model.
- [Needs taxonomy](docs/03-needs-taxonomy.md): operational categories for intake, triage, routing, and analytics.
- [Data governance](docs/04-data-governance.md): privacy, safety, verification, and humanitarian data rules.
- [Field context](docs/05-field-context.md): firsthand diaspora/frontline context to guide immediate priorities.
- [Trusted data pipeline](docs/06-trusted-data-pipeline.md): Hugging Face Space source registry, trusted feed snapshot, and ingestion rules.
- [Community report schema](data/schema/community_report.schema.json): starter JSON schema for field and community reports.
- [Sources](docs/sources.md): source register used for this foundation.

## MVP Wedge

The strongest public first release is:

**connectivity/support-location mapping + trusted hazard layers + redacted public needs signals.**

This is narrower than a general disaster map and safer than an AI-only social-media monitor. It fits Venezuela's current constraints: no power in parts of La Guaira, intermittent internet, unclear Starlink/connectivity hotspot locations, uncertain official information, high diaspora involvement, limited smartphone access among affected residents, and a pre-existing humanitarian crisis.

## Non-Negotiables

- No automated rescue, aid eligibility, medical, or protection decisions.
- No public map of identifiable vulnerable people, shelters at risk, GBV reports, undocumented migrants, or politically sensitive locations.
- Every AI output must carry source, timestamp, confidence, and human verification status.
- Personal data must be minimized, access-controlled, encrypted, and time-limited.
- The platform must export data to open formats and integrate with existing humanitarian tools such as KoBoToolbox/ODK, OSM, HDX/CODs, GDACS, Copernicus, and partner spreadsheets.

## Trusted Data Strategy

The app separates data into trust tiers:

1. **Trusted open context:** HDX/HOT/OSM/Overture, Google Research Open Buildings, Microsoft AI for Good Lab, USGS, UNEP/OCHA, HeiGIT, and other source-attributed public datasets.
2. **Partner operational data:** role-gated shelter, clinic, WASH, connectivity, logistics, and capacity updates from verified local or humanitarian partners.
3. **Community/proxy reports:** unverified observations that require deduplication, source checks, contact, and human review.
4. **AI-derived metadata:** advisory labels, urgency suggestions, geocoding hints, summaries, and duplicate candidates.
5. **Public outputs:** redacted or aggregate data approved for publication.

The current trusted snapshot includes 17 active sources, 57 HDX resources, 2 Google public building datasets, 5 public satellite imagery sources, 9,128 Microsoft damage footprints, 6 HOTOSM earthquake damage AOIs, and 7 USGS earthquake events. The incident query envelope covers all Venezuela, while verified building-level damage remains limited to sourced footprints such as Microsoft/HDX Catia. See [Trusted data pipeline](docs/06-trusted-data-pipeline.md).

## First Build Recommendation

Start with a read-only public viewer:

1. Connectivity/support map: Starlink or other connectivity hotspots, charging points, support centers, shelters, clinics, food/water points, and collection centers.
2. Trusted hazard context: Microsoft AI for Good building damage, Google Open Buildings exposure context, USGS earthquake context, HOT/OSM basemaps, and HDX/OCHA metadata.
3. Redacted public signals: consolidated needs, support gaps, and infrastructure observations that are approved for publication.
4. Human review upstream: partner validation, deduplication, and safety checks happen outside the public Space before data is published.
5. Communication: verified public updates, source attribution, and clear confidence/verification labels.
6. Governance: retention policy, open exports, source registry, and data-sharing agreement templates for upstream partners.

## Microsoft AI For Good Damage Layer

The prototype integrates Microsoft AI for Good Lab's HDX dataset, **Venezuela Earthquakes: Building Damage Assessment in Catia La Mar**, through the public ArcGIS `Edificios_Afectados` FeatureServer layer. For fast public viewing, the first map view uses pre-rendered transparent damage tiles in `public/data/damage-tiles/`, generated from `public/data/microsoft-damage-catia-lite.geojson`. The browser does not construct thousands of building polygons on startup; source attribution and refresh scripts still point back to ArcGIS/HDX.

Refresh the local damage snapshot with:

```bash
npm run cache:damage
npm run cache:damage-tiles
```

## High-Resolution Satellite Slider

The default public map uses EOX Sentinel-2 Cloudless 2024 for open, shareable Venezuela-wide optical context at 10 m resolution. National-only zoom is capped at the Sentinel-2 layer's useful native detail so the app does not present enlarged low-resolution tiles as building-scale evidence. The opt-in comparison view uses Vantor Open Data STAC COG scenes cataloged through NASA Earthdata GIS: one LG02 pre-event layer from 7 Apr 2026 and one LG05 post-event layer from 27 Jun 2026, rendered through HOTOSM TiTiler at 2x tile scale and clipped to their shared source footprint. Inside that footprint, high-zoom non-comparison views can also load the post-event Vantor layer. The Microsoft/HDX affected-building damage raster is separate and opt-in so the default comparison stays focused on the real before/after satellite imagery.

Treat the national Sentinel-2 layer and the Vantor slider as public visual context, not as automated damage classification; the Microsoft/HDX assessment and human validation remain the damage interpretation sources. The app avoids the previous multi-scene optical mosaic in the primary slider because mixed scene footprints can look like artificial damage rectangles or repeated buildings.

High-zoom Catia La Mar views also load `public/data/osm-named-places-catia.geojson`, a static OpenStreetMap/Overpass cache of named buildings, shops, civic places, hotels, offices, leisure places, and transit/aeroway places inside the verified comparison footprint. These labels are exact OSM `name` tags with OSM source URLs; unnamed buildings remain unlabeled, and labels must not be treated as damage verification or as an official government registry.

The **Key pins** control is an owner-only manual draft workflow for field review. It is hidden from the public Hugging Face build by default and only renders when the frontend is built with `VITE_OWNER_TOOLS=true`. When enabled, it focuses the verified Catia/Vantor corridor, leaves Microsoft/HDX damage off by default, lets an operator place three ranked key affected-area pins, and copies a JSON block with exact latitude/longitude pairs. Those manual pins are not published evidence until the exported coordinates are reviewed and committed into the hotspot data.

The app can optionally prefer locally generated enhanced Vantor tiles under `public/data/enhanced-satellite-tiles/` for the shared verified damage corridor, while keeping raw Vantor COG tiles underneath as the evidence fallback. The enhancement pipeline is deterministic and non-generative: it fetches 512 px source tiles from the original Vantor GeoTIFFs, samples each scene for a consistent luminance stretch, applies mild local sharpening and conservative color adjustment, then writes retina JPEG map tiles plus a `manifest.json`. It does not use GAN, diffusion, or learned texture synthesis.

Generate enhanced comparison tiles with:

```bash
npm run cache:enhanced-satellite
```

Useful controls:

```bash
ENHANCED_TILE_ZOOMS=18,19 ENHANCED_TILE_CONCURRENCY=12 ENHANCED_TILE_QUALITY=92 npm run cache:enhanced-satellite
ENHANCED_TILE_CALIBRATION_TILES=128 npm run cache:enhanced-satellite
ENHANCED_TILE_LIMIT=20 npm run cache:enhanced-satellite
```

Run the full-size Hugging Face Jobs pipeline with a write-capable local HF token:

```bash
hf jobs uv run --detach --flavor cpu-performance --timeout 6h --secrets HF_TOKEN \
  --env OUTPUT_REPO=sergiopesch/ayudavenezuela2026-enhanced-satellite-tiles \
  --env ENHANCED_TILE_ZOOMS=18,19 \
  --env ENHANCED_TILE_CONCURRENCY=36 \
  --env ENHANCED_TILE_QUALITY=92 \
  --env ENHANCED_TILE_CALIBRATION_TILES=128 \
  --env ENHANCED_TILE_ARCHIVE=/tmp/ayudavenezuela2026-enhanced-satellite-tiles-z18-z19-20260702.tar \
  scripts/hf-enhanced-satellite-job.py
```

The 2 Jul 2026 full run wrote `23,440` pre-event tiles and `23,028` post-event tiles to the private dataset `sergiopesch/ayudavenezuela2026-enhanced-satellite-tiles` as `ayudavenezuela2026-enhanced-satellite-tiles-z18-z19-20260702.tar` plus `manifest.json`. Verify the archive with:

```bash
hf jobs uv run --detach --flavor cpu-upgrade --timeout 2h --secrets HF_TOKEN \
  --env OUTPUT_REPO=sergiopesch/ayudavenezuela2026-enhanced-satellite-tiles \
  --env ENHANCED_TILE_ARCHIVE_NAME=ayudavenezuela2026-enhanced-satellite-tiles-z18-z19-20260702.tar \
  scripts/hf-verify-enhanced-satellite-archive.py
```

The verification job checks all tile JPEGs inside the archive, compares tar counts to the manifest, and uploads `verification/enhanced-satellite-verification-report-20260702.json` plus `verification/enhanced-satellite-sample-contact-sheet-20260702.jpg`.

For true learned super-resolution, run the Real-ESRGAN pilot as a separate interpretive artifact:

```bash
SR_AOIS_JSON_B64=<base64-json-aoi-list> \
hf jobs uv run --detach --flavor t4-small --timeout 45m --secrets HF_TOKEN \
  --env OUTPUT_REPO=sergiopesch/ayudavenezuela2026-enhanced-satellite-tiles \
  --env SR_AOI_LIMIT=36 \
  --env SR_ZOOM=19 \
  --env SR_ARCHIVE_NAME=ayudavenezuela2026-real-esrgan-affected-areas-z19-aoi36-20260702.tar \
  --env SR_AOIS_JSON_B64="$SR_AOIS_JSON_B64" \
  scripts/hf-real-esrgan-satellite-pilot.py
```

The 2 Jul 2026 affected-area run uses `RealESRGAN_x4plus` on 36 high-damage AOIs inside the before/after Vantor overlap. It uploads `super-resolution/real-esrgan-pilot/report-20260702.json`, `super-resolution/real-esrgan-pilot/contact-sheet-20260702.jpg`, and `super-resolution/real-esrgan-pilot/ayudavenezuela2026-real-esrgan-affected-areas-z19-aoi36-20260702.tar`. Cache the public app preview with `SR_ARCHIVE_NAME=ayudavenezuela2026-real-esrgan-affected-areas-z19-aoi36-20260702.tar npm run cache:sr-pilot`. This is a learned model output with nonzero hallucination risk, so it must stay labeled as interpretive visual aid and be shown beside the raw tile.

Keep these tiles labeled as enhanced visualization. The raw Vantor COG source remains the evidence layer and fallback.

## NASA Earthdata GIS Layers

NASA Earthdata GIS currently provides two relevant public event products for this incident. The app uses the NISAR line-of-sight displacement ImageServer as an opt-in overlay for broad deformation context. NASA also catalogs an experimental Sentinel-1 damaged-structures web map; it remains registered as trusted context but is not loaded by default because it is preliminary, unvalidated, and too large to render as client-side building polygons in the public first view.

These NASA products are not optical building-level before/after imagery. The public optical slider uses NASA-cataloged Vantor Open Data STAC COG scenes for before/after satellite context, while NASA/NISAR provides displacement context.

Sentinel-2 tiles are still cacheable for regional 10 m context if needed:

Refresh the local Sentinel tile cache with:

```bash
npm run cache:sentinel
```

## Google Public Data

The trusted-source registry now includes Google Research's **Open Buildings V3 Polygons** and **Open Buildings 2.5D Temporal Dataset**. These are used as public exposure/reference context for building footprints, settlement density, and annual building presence/count/height estimates. They should support aggregate public maps and partner validation, not household-level claims or automated eligibility decisions.

## Trusted Data Pipeline

The Hugging Face Space build runs `npm run build:data` before compiling the frontend. This creates `public/data/trusted-data.json`, a public-safe snapshot of trusted source metadata, HDX resource counts, USGS earthquake events, and ArcGIS damage-layer statistics. The same snapshot is available from `/api/trusted-data` in the Space backend.

Community reports in the prototype remain sample fixtures. Operational use should replace them through validated KoBo/ODK, partner CSV/API, call-center, WhatsApp/Telegram, and field-team intake pipelines with role-gated review.

## Running The Prototype

```bash
npm install
npm run dev
```

Open `http://localhost:5173/`.

The app runs without credentials using deterministic local triage. To enable live Hugging Face triage, set `HF_TOKEN` in a local `.env` or shell environment before running `npm run dev`. The token is used only by the local API proxy in `server/index.mjs`; it is not exposed as a `VITE_*` browser variable.
