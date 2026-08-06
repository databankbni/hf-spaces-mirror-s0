import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { mkdir } from 'node:fs/promises';

const sourcePath = resolve('public/data/microsoft-damage-catia-lite.geojson');
const outputPath = resolve('public/data/damage-view-index.json');
const severityCode = {
  high: 0,
  moderate: 1,
  observed: 2,
  uncertain: 3
};

function coordinatePairs(geometry) {
  const pairs = [];
  const visit = (value) => {
    if (typeof value?.[0] === 'number' && typeof value?.[1] === 'number') {
      pairs.push(value);
      return;
    }
    value?.forEach(visit);
  };
  visit(geometry.coordinates);
  return pairs;
}

function centroid(feature) {
  const areaCenter = geometryCentroid(feature.geometry);
  if (areaCenter) return areaCenter;

  const pairs = coordinatePairs(feature.geometry);
  if (!pairs.length) return null;
  const sum = pairs.reduce(
    (acc, [lon, lat]) => {
      acc.lon += lon;
      acc.lat += lat;
      return acc;
    },
    { lon: 0, lat: 0 }
  );
  return [sum.lon / pairs.length, sum.lat / pairs.length];
}

function ringCentroid(ring) {
  let twiceArea = 0;
  let cx = 0;
  let cy = 0;

  for (let index = 0; index < ring.length - 1; index += 1) {
    const [x0, y0] = ring[index];
    const [x1, y1] = ring[index + 1];
    const cross = x0 * y1 - x1 * y0;
    twiceArea += cross;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
  }

  if (Math.abs(twiceArea) < 1e-12) return null;
  return {
    area: twiceArea / 2,
    lon: cx / (3 * twiceArea),
    lat: cy / (3 * twiceArea)
  };
}

function polygonCentroid(rings) {
  const centers = rings.map(ringCentroid).filter(Boolean);
  if (!centers.length) return null;

  const weighted = centers.reduce(
    (acc, center) => {
      acc.area += center.area;
      acc.lon += center.lon * center.area;
      acc.lat += center.lat * center.area;
      return acc;
    },
    { area: 0, lon: 0, lat: 0 }
  );

  if (Math.abs(weighted.area) < 1e-12) return null;
  return [weighted.lon / weighted.area, weighted.lat / weighted.area];
}

function geometryCentroid(geometry) {
  if (geometry.type === 'Polygon') return polygonCentroid(geometry.coordinates);
  if (geometry.type !== 'MultiPolygon') return null;

  const centers = geometry.coordinates
    .map((polygon) => {
      const center = polygonCentroid(polygon);
      if (!center) return null;
      const shell = ringCentroid(polygon[0]);
      if (!shell) return null;
      return { lon: center[0], lat: center[1], area: Math.abs(shell.area) };
    })
    .filter(Boolean);

  if (!centers.length) return null;
  const weighted = centers.reduce(
    (acc, center) => {
      acc.area += center.area;
      acc.lon += center.lon * center.area;
      acc.lat += center.lat * center.area;
      return acc;
    },
    { area: 0, lon: 0, lat: 0 }
  );

  if (!weighted.area) return null;
  return [weighted.lon / weighted.area, weighted.lat / weighted.area];
}

function damageScore(properties) {
  const values = [properties.damage_pct_0m, properties.damage_pct_10m, properties.damage_pct_20m].filter(
    (value) => typeof value === 'number' && Number.isFinite(value)
  );
  return values.length ? Math.max(...values) : 0;
}

function damageSeverity(properties) {
  if (properties.severity) return properties.severity;
  if (typeof properties.unknown_pct === 'number' && properties.unknown_pct >= 0.45) return 'uncertain';
  const score = damageScore(properties);
  if (score >= 0.7) return 'high';
  if (score >= 0.45) return 'moderate';
  return 'observed';
}

const source = JSON.parse(await readFile(sourcePath, 'utf8'));
const points = source.features
  .map((feature) => {
    const center = centroid(feature);
    if (!center) return null;
    const severity = damageSeverity(feature.properties || {});
    return [
      Math.round(center[0] * 1_000_000) / 1_000_000,
      Math.round(center[1] * 1_000_000) / 1_000_000,
      severityCode[severity] ?? severityCode.observed
    ];
  })
  .filter(Boolean);

const bounds = points.reduce(
  (bbox, [lon, lat]) => ({
    west: Math.min(bbox.west, lon),
    south: Math.min(bbox.south, lat),
    east: Math.max(bbox.east, lon),
    north: Math.max(bbox.north, lat)
  }),
  { west: Infinity, south: Infinity, east: -Infinity, north: -Infinity }
);

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(
  outputPath,
  `${JSON.stringify({
    schemaVersion: 1,
    generatedFrom: 'public/data/microsoft-damage-catia-lite.geojson',
    source: 'Microsoft AI for Good Lab / HDX Catia La Mar building damage snapshot',
    total: points.length,
    bounds,
    severityCodes: {
      0: 'high',
      1: 'moderate',
      2: 'observed',
      3: 'uncertain'
    },
    points
  })}\n`
);

console.log(`damage view index: ${outputPath} (${points.length.toLocaleString()} points)`);
