import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

const damageIndexPath = resolve('public/data/damage-view-index.json');
const outputPath = resolve('public/data/worst-damage-hotspots.json');

const comparisonOverlap = {
  west: -67.043108,
  south: 10.524025,
  east: -66.96,
  north: 10.642557
};

const severityWeights = {
  0: 4,
  1: 2,
  2: 0.7,
  3: 0.1
};

const keyAffectedAreas = [
  {
    lat: 10.610353,
    lon: -67.012348,
    es: 'Edificio Arnedillo / Residencias Marena',
    en: 'Edificio Arnedillo / Residencias Marena',
    context: {
      es: 'punto clave seleccionado junto a nombres OSM verificados en Playa Grande',
      en: 'selected key point beside verified OSM names in Playa Grande'
    }
  },
  {
    lat: 10.609699,
    lon: -67.014644,
    es: 'Residencias Palmilla / Sol Marina Garden 2',
    en: 'Residencias Palmilla / Sol Marina Garden 2',
    context: {
      es: 'punto clave seleccionado cerca de residencias y hotel OSM verificados',
      en: 'selected key point near verified OSM residences and hotel names'
    }
  },
  {
    lat: 10.612984,
    lon: -67.022674,
    es: 'Playa Mar / Playa Grande este',
    en: 'Playa Mar / East Playa Grande',
    context: {
      es: 'punto clave seleccionado en edificios residenciales nombrados por OSM',
      en: 'selected key point in OSM-named residential buildings'
    }
  }
];

function inside(bounds, lon, lat) {
  return lon >= bounds.west && lon <= bounds.east && lat >= bounds.south && lat <= bounds.north;
}

function scoreCandidate(points) {
  const summary = { total: points.length, high: 0, moderate: 0, observed: 0, uncertain: 0 };
  let severityScore = 0;

  for (const [, , severity] of points) {
    severityScore += severityWeights[severity] || 0;
    if (severity === 0) summary.high += 1;
    else if (severity === 1) summary.moderate += 1;
    else if (severity === 2) summary.observed += 1;
    else summary.uncertain += 1;
  }

  return {
    ...summary,
    score: severityScore + summary.total * 0.2
  };
}

function distanceMeters(left, right) {
  const lonMeters = (left.lon - right.lon) * 109000;
  const latMeters = (left.lat - right.lat) * 111000;
  return Math.sqrt(lonMeters * lonMeters + latMeters * latMeters);
}

const halfWindow = 0.0018;
const damageIndex = JSON.parse(await readFile(damageIndexPath, 'utf8'));
const overlapPoints = damageIndex.points.filter(([lon, lat]) => inside(comparisonOverlap, lon, lat));

const selected = keyAffectedAreas.map((area) => {
  if (!inside(comparisonOverlap, area.lon, area.lat)) {
    throw new Error(`Key affected area outside comparison overlap: ${area.lat},${area.lon}`);
  }
  const points = overlapPoints.filter(([pointLon, pointLat]) => (
    Math.abs(pointLon - area.lon) <= halfWindow && Math.abs(pointLat - area.lat) <= halfWindow
  ));
  return {
    ...area,
    ...scoreCandidate(points)
  };
});

const hotspots = selected.map((area, index) => ({
  id: `verified-hotspot-${index + 1}`,
  rank: index + 1,
  lat: area.lat,
  lng: area.lon,
  labels: {
    es: area.es,
    en: area.en
  },
  context: area.context,
  total: area.total,
  high: area.high,
  moderate: area.moderate,
  observed: area.observed,
  uncertain: area.uncertain,
  score: Math.round(area.score * 10) / 10,
  method: {
    type: 'user-selected-key-affected-area',
    windowDegrees: halfWindow * 2,
    source: damageIndex.source,
    note: 'User-selected key affected area inside the Vantor before/after overlap. Area labels use nearby exact OpenStreetMap names; damage metrics are computed from Microsoft/HDX affected-building centroids in the local window and remain source-attributed.'
  }
}));

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(
  outputPath,
  `${JSON.stringify({
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    source: damageIndex.source,
    comparisonOverlap,
    hotspots
  }, null, 2)}\n`,
  'utf8'
);

console.log(`key affected areas: ${outputPath} (${hotspots.length} areas)`);
