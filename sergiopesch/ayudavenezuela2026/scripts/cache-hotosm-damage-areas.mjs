import { gzip } from 'node:zlib';
import { promisify } from 'node:util';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

const gzipAsync = promisify(gzip);
const datasetBase = 'https://huggingface.co/datasets/hotosm/venezuela_eq_2026/resolve/main';
const outputPath = resolve('public/data/hotosm-venezuela-damage-areas.geojson');
const outputGzipPath = `${outputPath}.gz`;
const areas = [
  ['caracas', 'Caracas'],
  ['caraballeda', 'Caraballeda'],
  ['catia_la_mar', 'Catia La Mar'],
  ['la_guaira', 'La Guaira'],
  ['moron', 'Moron'],
  ['naiguata', 'Naiguata']
];

async function fetchJson(path) {
  const response = await fetch(`${datasetBase}/${path}`, {
    headers: { accept: 'application/geo+json,application/json' }
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`HOTOSM fetch failed ${response.status}: ${path}`);
  return response.json();
}

function featureCount(geojson) {
  return Array.isArray(geojson?.features) ? geojson.features.length : 0;
}

function walkCoordinates(coordinates, visit) {
  if (!Array.isArray(coordinates)) return;
  if (typeof coordinates[0] === 'number') {
    visit(coordinates[0], coordinates[1]);
    return;
  }
  for (const child of coordinates) walkCoordinates(child, visit);
}

function bboxOfFeature(feature) {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  walkCoordinates(feature.geometry?.coordinates, (lon, lat) => {
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) return;
    west = Math.min(west, lon);
    south = Math.min(south, lat);
    east = Math.max(east, lon);
    north = Math.max(north, lat);
  });
  return [west, south, east, north];
}

function centerOfBbox([west, south, east, north]) {
  return [(west + east) / 2, (south + north) / 2];
}

async function summarizeArea(slug, label) {
  const aoi = await fetchJson(`${slug}/aoi.geojson`);
  if (!aoi?.features?.length) throw new Error(`Missing AOI for ${slug}`);

  const [
    combinedDamage,
    fairMajorDestroyed,
    humanValidatedDamage,
    microsoftDamage,
    osuDamage
  ] = await Promise.all([
    fetchJson(`${slug}/damage_assessment/combined/${slug}_combined_damage_points.geojson`),
    fetchJson(`${slug}/damage_assessment/fair/${slug}_major_destroyed_points.geojson`),
    fetchJson(`${slug}/damage_assessment/validated/validated_mapswipe/${slug}_human_validated_damage_polygons.geojson`),
    fetchJson(`${slug}/damage_assessment/microsoft/${slug}_microsoft_damaged_points.geojson`),
    fetchJson(`${slug}/damage_assessment/osu/${slug}_osu_damaged_points.geojson`)
  ]);

  return aoi.features.map((feature, index) => {
    const bbox = bboxOfFeature(feature);
    const [lon, lat] = centerOfBbox(bbox);
    return {
      type: 'Feature',
      geometry: feature.geometry,
      properties: {
        id: `${slug}-${index + 1}`,
        slug,
        label,
        bbox,
        center: [lon, lat],
        combinedDamagePoints: featureCount(combinedDamage),
        fairMajorDestroyedPoints: featureCount(fairMajorDestroyed),
        humanValidatedDamagePolygons: featureCount(humanValidatedDamage),
        microsoftDamagePoints: featureCount(microsoftDamage),
        osuDamagePoints: featureCount(osuDamage),
        source: 'HOTOSM Venezuela earthquake AI building and damage assessment',
        sourceDataset: 'hotosm/venezuela_eq_2026',
        sourceUrl: `https://huggingface.co/datasets/hotosm/venezuela_eq_2026/tree/main/${slug}`,
        evidenceLimit:
          'AI-derived and/or human-validated damage context. Use for prioritization and visual context, not as verified household-level damage.',
        highResolutionSrEligible:
          slug === 'catia_la_mar',
        highResolutionSrLimit:
          slug === 'catia_la_mar'
            ? 'Intersects the available Vantor before/after high-resolution source corridor only in the shared Catia/La Guaira overlap.'
            : 'No registered before/after Vantor high-resolution optical source in this app; do not run learned SR for this area yet.'
      }
    };
  });
}

const features = (await Promise.all(areas.map(([slug, label]) => summarizeArea(slug, label)))).flat();
const payload = {
  type: 'FeatureCollection',
  name: 'hotosm_venezuela_eq_2026_damage_areas',
  generatedAt: new Date().toISOString(),
  sourceDataset: 'hotosm/venezuela_eq_2026',
  sourceUrl: 'https://huggingface.co/datasets/hotosm/venezuela_eq_2026',
  features
};

const body = `${JSON.stringify(payload, null, 2)}\n`;
await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, body);
await writeFile(outputGzipPath, await gzipAsync(Buffer.from(body)));
console.log(`HOTOSM damage areas: ${features.length} AOIs -> ${outputPath}`);
