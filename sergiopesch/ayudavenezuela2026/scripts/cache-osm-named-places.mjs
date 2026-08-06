import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const outputPath = path.join(process.cwd(), 'public/data/osm-named-places-catia.geojson');
const overpassUrls = (process.env.OVERPASS_URLS || process.env.OVERPASS_URL || [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter'
].join(',')).split(',').map((url) => url.trim()).filter(Boolean);
const bbox = {
  south: 10.524025,
  west: -67.043108,
  north: 10.642557,
  east: -66.967422
};

const sourceTags = [
  'building',
  'amenity',
  'healthcare',
  'emergency',
  'tourism',
  'historic',
  'shop',
  'office',
  'leisure',
  'public_transport',
  'railway',
  'aeroway'
];

const civicAmenityValues = new Set([
  'bank',
  'bus_station',
  'clinic',
  'college',
  'doctors',
  'fire_station',
  'fuel',
  'hospital',
  'kindergarten',
  'cafe',
  'fast_food',
  'pharmacy',
  'place_of_worship',
  'police',
  'post_office',
  'restaurant',
  'school',
  'townhall',
  'university'
]);

function overpassBbox() {
  return `${bbox.south},${bbox.west},${bbox.north},${bbox.east}`;
}

function buildQuery() {
  const clauses = sourceTags.flatMap((tag) => [
    `node["name"]["${tag}"](${overpassBbox()});`,
    `way["name"]["${tag}"](${overpassBbox()});`
  ]);

  return `[out:json][timeout:60];(\n  ${clauses.join('\n  ')}\n);out center tags;`;
}

function categoryFor(tags) {
  if (tags.healthcare || ['hospital', 'clinic', 'doctors', 'pharmacy'].includes(tags.amenity)) return 'health';
  if (['police', 'fire_station'].includes(tags.amenity) || tags.emergency) return 'safety';
  if (['school', 'college', 'university', 'kindergarten'].includes(tags.amenity)) return 'education';
  if (tags.tourism) return 'lodging';
  if (tags.aeroway || tags.public_transport || tags.railway) return 'amenity';
  if (tags.shop) return 'shop';
  if (['restaurant', 'fast_food', 'cafe', 'bar'].includes(tags.amenity)) return 'food';
  if (tags.amenity === 'bank') return 'finance';
  if (tags.amenity) return 'amenity';
  if (tags.office) return 'office';
  if (tags.leisure) return 'leisure';
  if (tags.historic) return 'historic';
  if (tags.building) return 'building';
  return 'place';
}

function labelKind(tags) {
  for (const tag of sourceTags) {
    if (tags[tag]) return `${tag}:${tags[tag]}`;
  }
  return 'named';
}

function isHighConfidenceLabel(tags) {
  if (tags.building) return true;
  if (tags.healthcare || tags.emergency || tags.historic) return true;
  if (tags.amenity && civicAmenityValues.has(tags.amenity)) return true;
  if (['hotel', 'guest_house', 'hostel'].includes(tags.tourism)) return true;
  if (tags.shop || tags.office || tags.leisure || tags.public_transport || tags.railway || tags.aeroway) return true;
  return false;
}

function coordinatesFor(element) {
  const lat = element.lat ?? element.center?.lat;
  const lon = element.lon ?? element.center?.lon;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (lat < bbox.south || lat > bbox.north || lon < bbox.west || lon > bbox.east) return null;
  return [Number(lon), Number(lat)];
}

function normalizeName(value) {
  return String(value || '').trim().replace(/\s+/g, ' ');
}

function elementToFeature(element) {
  const tags = element.tags || {};
  const name = normalizeName(tags['name:es'] || tags.name);
  const coordinates = coordinatesFor(element);
  if (!name || !coordinates) return null;
  if (!isHighConfidenceLabel(tags)) return null;

  return {
    type: 'Feature',
    geometry: {
      type: 'Point',
      coordinates
    },
    properties: {
      id: `${element.type}/${element.id}`,
      osmType: element.type,
      osmId: element.id,
      name,
      category: categoryFor(tags),
      kind: labelKind(tags),
      source: 'OpenStreetMap',
      sourceUrl: `https://www.openstreetmap.org/${element.type}/${element.id}`,
      tags
    }
  };
}

function dedupe(features) {
  const seen = new Set();
  return features.filter((feature) => {
    const [lon, lat] = feature.geometry.coordinates;
    const key = `${feature.properties.name.toLowerCase()}|${lat.toFixed(5)}|${lon.toFixed(5)}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function sortFeatures(features) {
  const weights = {
    safety: 0,
    health: 1,
    education: 2,
    building: 3,
    amenity: 4,
    finance: 5,
    shop: 6,
    food: 7,
    lodging: 8,
    office: 9,
    leisure: 10,
    historic: 11,
    place: 12
  };

  return features.sort((a, b) => {
    const categoryDelta = (weights[a.properties.category] ?? 99) - (weights[b.properties.category] ?? 99);
    if (categoryDelta) return categoryDelta;
    return a.properties.name.localeCompare(b.properties.name);
  });
}

const query = buildQuery();
async function fetchOverpass() {
  const failures = [];

  for (const url of overpassUrls) {
    const response = await fetch(url, {
      method: 'POST',
      body: new URLSearchParams({ data: query }),
      headers: {
        'content-type': 'application/x-www-form-urlencoded',
        'user-agent': 'AyudaVenezuela2026 named place cache'
      }
    });

    if (response.ok) {
      return { url, payload: await response.json() };
    }
    failures.push(`${url}: ${response.status} ${response.statusText}`);
  }

  throw new Error(`Overpass request failed: ${failures.join('; ')}`);
}

const { url: sourceUrl, payload } = await fetchOverpass();
const features = sortFeatures(dedupe((payload.elements || []).map(elementToFeature).filter(Boolean)));
const collection = {
  type: 'FeatureCollection',
  name: 'osm_named_places_catia_la_mar',
  generatedAt: new Date().toISOString(),
  source: {
    name: 'OpenStreetMap via Overpass API',
    url: sourceUrl,
    license: 'ODbL',
    query,
    bbox
  },
  accuracyNote:
    'Labels are exact names from OpenStreetMap tags at generatedAt. Unnamed buildings are intentionally not labeled.',
  features
};

await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(collection, null, 2)}\n`);
console.log(`OSM named places: ${features.length} labels -> ${outputPath}`);
