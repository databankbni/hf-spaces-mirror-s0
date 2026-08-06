# Trusted Data Pipeline

## Goal

The application should use highly trusted public and partner data as the backbone, while treating community and proxy reports as unverified observations until a human validates them.

## Hugging Face Space Pipeline

The Space builds a public-safe data snapshot during Docker build:

```bash
npm run build:data
```

The script reads `data/trusted-source-registry.json`, fetches metadata and non-sensitive summaries from trusted sources, and writes:

```text
public/data/trusted-data.json
```

In production, Vite copies this to `dist/data/trusted-data.json`. The Express server also exposes the same snapshot at:

```text
/api/trusted-data
```

The snapshot intentionally stores source metadata, resource counts, event summaries, and layer statistics. It does not import personal reports, raw social media posts, or sensitive casework.

The public map also keeps two runtime-heavy layers as local public assets:

```bash
npm run cache:damage
npm run cache:sentinel
```

`cache:damage` writes `public/data/microsoft-damage-catia-lite.geojson` from the Microsoft/ArcGIS `Edificios_Afectados` layer so refresh jobs do not depend on paginated ArcGIS queries at runtime. `cache:damage-tiles` converts that lightweight snapshot into transparent raster tiles under `public/data/damage-tiles/`, which is what the public map loads on startup. `cache:sentinel` writes JPEG files under `public/data/sentinel-tiles/` from the Element 84/AWS Sentinel-2 COGs through TiTiler for optional regional 10 m context.

The default national optical map uses EOX Sentinel-2 Cloudless 2024 WMTS tiles. This gives open, shareable Venezuela-wide context without generating or hallucinating building-scale detail. National-only map interaction is capped at the Sentinel-2 layer's useful native detail; high-zoom interaction is reserved for source-backed Vantor comparison views or damage rasters inside their verified footprints.

The primary public comparison uses one pre-event Vantor LG06 OpenAerialMap scene from 21 Mar 2026 and one post-event Vantor LG05 OpenAerialMap scene from 27 Jun 2026, both cataloged by NASA Earthdata GIS. The Microsoft/HDX affected-building damage raster is opt-in so the default slider compares the optical satellite images directly. The app avoids broad mixed-scene optical mosaics because mixed scene footprints can look like artificial rectangular damage or repeated buildings.

NASA Earthdata GIS also provides an opt-in NISAR line-of-sight displacement ImageServer product derived from 13 Jun and 25 Jun 2026 SAR imagery at 80 m posting. The public viewer uses it as broad deformation context only. NASA/OSU's experimental Sentinel-1 damaged-structures web map remains in the trusted-source registry, but is not loaded by default because it is preliminary, unvalidated, and too large for client-side public rendering as individual building polygons.

The affected-coverage overlay uses a national Venezuela envelope for search, aftershock/source queries, and public context. It also shows narrower analyzed corridors and verified damage footprints when those sources exist. The national outline must not be interpreted as verified building damage across the whole country.

## Automated Sources

The first automated source set is:

- HDX/HOT earthquake OSM and Overture package for roads, buildings, facilities, ports, airports, points of interest, and data quality context.
- Google Research Open Buildings V3 Polygons for baseline public building-footprint exposure and settlement density context.
- Google Research Open Buildings 2.5D Temporal Dataset for annual 2016-2023 building presence, fractional count, and height context.
- EOX Sentinel-2 Cloudless 2024 WMTS for open Venezuela-wide optical context at 10 m resolution.
- Vantor imagery via NASA Earthdata GIS/OpenAerialMap for the public high-resolution 21 Mar / 27 Jun before-after satellite slider.
- NASA/NISAR line-of-sight displacement ImageServer for public broad deformation context from 13 Jun / 25 Jun 2026 SAR imagery.
- NASA/OSU Sentinel-1 experimental damaged-structures web map as registered context, not loaded by default in the public view.
- HOTOSM `hotosm/venezuela_eq_2026` Hugging Face dataset for Caracas, Caraballeda, Catia La Mar, La Guaira, Moron, and Naiguata damage-AOI context and source-count summaries.
- Sentinel-2 L2A Cloud-Optimized GeoTIFF visual assets from Element 84 Earth Search / AWS Open Data for optional regional 22 Jun / 27 Jun context.
- Microsoft AI for Good Lab HDX package for Catia La Mar building damage assessment.
- Microsoft/ArcGIS `Edificios_Afectados` FeatureServer for affected-building layer statistics.
- UNEP/OCHA hazardous facilities package.
- HeiGIT accessibility indicators.
- HOT health facilities, roads, and populated places.
- USGS earthquake event GeoJSON for event IDs, magnitudes, locations, and aftershock context.

ReliefWeb remains in the registry as a manual situation-monitoring source until an event-specific query is validated.

## Trust Rules

- Trusted public datasets provide context, not case-level truth.
- Partner operational layers outrank public open data when a partner has current field verification.
- Community reports never become public map facts without validation and redaction.
- Microsoft AI damage polygons may prioritize review and routing, but must not trigger automated rescue, aid eligibility, or public household-level claims.
- National affected coverage means the app can search, pan, and monitor across Venezuela; it does not mean every visible location has verified damage evidence.
- Google Open Buildings data may support public aggregate exposure estimates, but must not be interpreted as verified occupancy, household identity, or post-earthquake damage.
- Vantor/OpenAerialMap imagery cataloged by NASA is useful for building-scale before/after source context; use the Microsoft/HDX assessment and human validation for damage interpretation.
- NASA/NISAR displacement is useful for broad deformation context at 80 m posting, not for building-level damage validation.
- NASA/OSU Sentinel-1 damaged-structures output is preliminary and unvalidated; keep the source caveats visible and do not treat it as a verified building-by-building census.
- Learned Real-ESRGAN super-resolution is an opt-in visual aid for AOIs that overlap the Vantor before/after source imagery. Do not use it to claim new damage evidence, especially outside the verified Catia/La Guaira optical footprint.
- The western pre-event fallback has visible cloud/haze, so western before/post visual comparisons are lower confidence than the clearer central/eastern sectors.
- Sentinel-2 is useful for public regional and national context at 10 m resolution, but it cannot confirm individual building-level damage.
- Cached Sentinel-2 tiles are a delivery optimization for optional regional context, not a separate analytical product. Refresh them when changing the incident area, date pair, or zoom level.
- OpenAerialMap item metadata reports CC BY-NC 4.0 for the selected Vantor scenes; attribute Vantor and OpenAerialMap and review license implications before commercial reuse.
- Licenses and attribution are tracked per source. ODbL, CC BY, CC BY-SA, and source-specific report terms are not interchangeable.

## Next Data Work

1. Add PostGIS tables for source catalog, assets, hazards, reports, review actions, and public exports.
2. Add KoBo/ODK import against `data/schema/community_report.schema.json`.
3. Add partner CSV/Google Sheet import with source registry mapping.
4. Add duplicate detection between community reports, partner rows, and known assets.
5. Add H3 or admin-area aggregation for public-safe needs maps.
6. Add Earth Engine/Cloud export for Google Open Buildings clipped to the La Guaira/Caracas incident area, then store only public aggregate counts or tiles in the Space.
7. Add scheduled refresh through a Hugging Face Job or external scheduler once the prototype becomes operational.
