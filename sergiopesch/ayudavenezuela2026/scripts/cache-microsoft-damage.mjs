import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { gzipSync } from 'node:zlib';

const featureLayerUrl =
  'https://services8.arcgis.com/w0z3NDBGLWwOLx2y/arcgis/rest/services/Catia_La_Mar_3D_WFL1/FeatureServer/0';
const outFields = 'OBJECTID,id,damage_pct_0m,damage_pct_10m,damage_pct_20m,damaged,unknown_pct';
const pageSize = 2000;
const outputPath = resolve('public/data/microsoft-damage-catia-lite.geojson');
const compressedOutputPath = `${outputPath}.gz`;

function pageUrl(resultOffset) {
  const url = new URL(`${featureLayerUrl}/query`);
  url.search = new URLSearchParams({
    f: 'geojson',
    where: '1=1',
    outFields,
    outSR: '4326',
    returnGeometry: 'true',
    orderByFields: 'OBJECTID',
    resultOffset: String(resultOffset),
    resultRecordCount: String(pageSize)
  }).toString();
  return url;
}

function isFeatureCollection(value) {
  return value?.type === 'FeatureCollection' && Array.isArray(value.features);
}

function exceededTransferLimit(value) {
  return value?.properties?.exceededTransferLimit === true;
}

const features = [];

for (let offset = 0; ; offset += pageSize) {
  const response = await fetch(pageUrl(offset));
  if (!response.ok) {
    throw new Error(`ArcGIS damage request failed at offset ${offset}: ${response.status}`);
  }

  const payload = await response.json();
  if (!isFeatureCollection(payload)) {
    throw new Error(`ArcGIS damage request returned an unexpected payload at offset ${offset}`);
  }

  features.push(...payload.features);
  console.log(`Cached ${features.length.toLocaleString()} damage footprints`);

  if (payload.features.length < pageSize || !exceededTransferLimit(payload)) break;
}

await mkdir(dirname(outputPath), { recursive: true });

function damageSeverity(properties) {
  const values = [properties.damage_pct_0m, properties.damage_pct_10m, properties.damage_pct_20m].filter(
    (value) => typeof value === 'number' && Number.isFinite(value)
  );
  const score = values.length ? Math.max(...values) : 0;
  if (properties.unknown_pct !== null && properties.unknown_pct >= 0.45) return 'uncertain';
  if (score >= 0.7) return 'high';
  if (score >= 0.45) return 'moderate';
  return 'observed';
}

function roundCoordinates(coordinates) {
  if (typeof coordinates[0] === 'number') {
    return [
      Math.round(coordinates[0] * 100000) / 100000,
      Math.round(coordinates[1] * 100000) / 100000
    ];
  }
  return coordinates.map(roundCoordinates);
}

const liteFeatures = features.map((feature) => ({
  type: 'Feature',
  geometry: {
    type: feature.geometry.type,
    coordinates: roundCoordinates(feature.geometry.coordinates)
  },
  properties: {
    id: feature.properties.id ?? feature.properties.OBJECTID,
    severity: damageSeverity(feature.properties)
  }
}));

const output = `${JSON.stringify({
  type: 'FeatureCollection',
  metadata: {
    source: featureLayerUrl,
    cachedAt: new Date().toISOString(),
    recordCount: liteFeatures.length,
    geometryPrecision: 5,
    fields: ['id', 'severity']
  },
  features: liteFeatures
})}\n`;

await writeFile(outputPath, output);
await writeFile(compressedOutputPath, gzipSync(output, { level: 9 }));

console.log(`Wrote ${outputPath}`);
console.log(`Wrote ${compressedOutputPath}`);
