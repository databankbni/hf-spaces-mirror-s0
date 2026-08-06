import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import jpeg from 'jpeg-js';

const outputRoot = resolve(process.env.ENHANCED_TILE_ROOT || 'public/data/enhanced-satellite-tiles');
const zoomLevels = (process.env.ENHANCED_TILE_ZOOMS || '18,19')
  .split(',')
  .map((value) => Number(value.trim()))
  .filter((value) => Number.isInteger(value) && value >= 0);
const concurrency = Math.max(1, Number(process.env.ENHANCED_TILE_CONCURRENCY || 12));
const jpegQuality = Math.max(70, Math.min(98, Number(process.env.ENHANCED_TILE_QUALITY || 92)));
const cleanOutput = process.env.ENHANCED_TILE_CLEAN !== '0';
const smokeLimit = Number(process.env.ENHANCED_TILE_LIMIT || 0);
const calibrationTileCount = Math.max(8, Number(process.env.ENHANCED_TILE_CALIBRATION_TILES || 96));
const tileMode = process.env.ENHANCED_TILE_MODE || 'bounds';
const hotspotInputPath = process.env.ENHANCED_TILE_HOTSPOTS || 'public/data/worst-damage-hotspots.json';
const hotspotPath = resolve(hotspotInputPath);
const hotspotTileRadius = Math.max(0, Number(process.env.ENHANCED_TILE_RADIUS || 3));

const transparentJpeg = Buffer.from(
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Aqf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2gAMAwEAAgADAAAAEP/EFBQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EFBQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EFBABAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAT8QH//Z',
  'base64'
);

const scenes = {
  before: {
    label: 'Vantor LG02 pre-event imagery, 7 Apr 2026',
    cogUrl: 'https://vantor-opendata.s3.amazonaws.com/events/Venezuela-Earthquake-Jun-2026/B120001100513B10.tif',
    bounds: { west: -67.085575, south: 10.518145, east: -66.967422, north: 10.679827 },
    gsdMeters: 0.415
  },
  after: {
    label: 'Vantor LG05 post-event imagery, 27 Jun 2026',
    cogUrl: 'https://vantor-opendata.s3.amazonaws.com/events/Venezuela-Earthquake-Jun-2026/B15000110186C610.tif',
    bounds: { west: -67.043108, south: 10.524025, east: -66.942944, north: 10.642557 },
    gsdMeters: 0.3494610093253814
  }
};

const verifiedDamageBounds = { west: -67.14, south: 10.54, east: -66.96, north: 10.65 };
const enhancedBounds = intersectBounds(verifiedDamageBounds, scenes.before.bounds, scenes.after.bounds);

function intersectBounds(...boundsList) {
  return boundsList.reduce(
    (bounds, next) => ({
      west: Math.max(bounds.west, next.west),
      south: Math.max(bounds.south, next.south),
      east: Math.min(bounds.east, next.east),
      north: Math.min(bounds.north, next.north)
    }),
    { west: -Infinity, south: -Infinity, east: Infinity, north: Infinity }
  );
}

function lonToTile(lon, z) {
  return Math.floor(((lon + 180) / 360) * 2 ** z);
}

function latToTile(lat, z) {
  const radians = (lat * Math.PI) / 180;
  return Math.floor(((1 - Math.log(Math.tan(radians) + 1 / Math.cos(radians)) / Math.PI) / 2) * 2 ** z);
}

function tileToLon(x, z) {
  return (x / 2 ** z) * 360 - 180;
}

function tileToLat(y, z) {
  const radians = Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / 2 ** z)));
  return (radians * 180) / Math.PI;
}

function tileUrl(cogUrl, z, x, y) {
  return `https://titiler.hotosm.org/cog/tiles/WebMercatorQuad/${z}/${x}/${y}@2x?url=${encodeURIComponent(cogUrl)}`;
}

async function fetchTile(scene, z, x, y, attempt = 1) {
  const response = await fetch(tileUrl(scene.cogUrl, z, x, y), {
    headers: { accept: 'image/jpeg,*/*;q=0.8' }
  });

  if (response.status === 404) return null;
  if ((response.status === 429 || response.status >= 500) && attempt < 4) {
    await sleep(450 * attempt ** 2);
    return fetchTile(scene, z, x, y, attempt + 1);
  }

  if (!response.ok) {
    throw new Error(`Tile fetch failed ${response.status} for ${z}/${x}/${y}`);
  }

  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('image')) return null;
  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes[0] !== 0xff || bytes[1] !== 0xd8) return null;
  return bytes.length > 100 ? bytes : null;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clamp(value) {
  return Math.max(0, Math.min(255, Math.round(value)));
}

function luminance(data, offset) {
  return 0.2126 * data[offset] + 0.7152 * data[offset + 1] + 0.0722 * data[offset + 2];
}

function percentile(sorted, fraction) {
  if (!sorted.length) return 0;
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(sorted.length * fraction)))];
}

function blurChannel(values, width, height) {
  const tmp = new Float32Array(values.length);
  const out = new Float32Array(values.length);

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      const left = y * width + Math.max(0, x - 1);
      const right = y * width + Math.min(width - 1, x + 1);
      tmp[index] = values[left] * 0.25 + values[index] * 0.5 + values[right] * 0.25;
    }
  }

  for (let y = 0; y < height; y += 1) {
    const up = Math.max(0, y - 1);
    const down = Math.min(height - 1, y + 1);
    for (let x = 0; x < width; x += 1) {
      const index = y * width + x;
      out[index] = tmp[up * width + x] * 0.25 + tmp[index] * 0.5 + tmp[down * width + x] * 0.25;
    }
  }

  return out;
}

function calibrationTiles(tiles) {
  if (smokeLimit > 0) return tiles.slice(0, smokeLimit);
  if (tiles.length <= calibrationTileCount) return tiles;
  const stride = Math.max(1, Math.floor(tiles.length / calibrationTileCount));
  return tiles.filter((_, index) => index % stride === 0).slice(0, calibrationTileCount);
}

function sampleLuminance(bytes, values) {
  const image = jpeg.decode(bytes, { useTArray: true, maxMemoryUsageInMB: 512 });
  const { width, height, data } = image;
  const pixels = width * height;
  const step = Math.max(1, Math.floor(pixels / 4096));

  for (let pixel = 0; pixel < pixels; pixel += step) {
    values.push(clamp(luminance(data, pixel * 4)));
  }
}

function tileQuality(bytes) {
  const image = jpeg.decode(bytes, { useTArray: true, maxMemoryUsageInMB: 512 });
  const { width, height, data } = image;
  const pixels = width * height;
  const step = Math.max(1, Math.floor(pixels / 4096));
  const histogram = new Array(32).fill(0);
  let samples = 0;
  let sum = 0;
  let sumSquared = 0;
  let min = 255;
  let max = 0;

  for (let pixel = 0; pixel < pixels; pixel += step) {
    const value = clamp(luminance(data, pixel * 4));
    samples += 1;
    sum += value;
    sumSquared += value * value;
    min = Math.min(min, value);
    max = Math.max(max, value);
    histogram[Math.max(0, Math.min(31, Math.floor(value / 8)))] += 1;
  }

  let entropy = 0;
  for (const bucket of histogram) {
    if (!bucket) continue;
    const probability = bucket / samples;
    entropy -= probability * Math.log2(probability);
  }

  const mean = sum / samples;
  return {
    entropy,
    range: max - min,
    samples,
    stddev: Math.sqrt(Math.max(0, sumSquared / samples - mean * mean))
  };
}

function isInformativeTile(bytes) {
  const quality = tileQuality(bytes);
  return quality.samples >= 100 && quality.range >= 30 && quality.stddev >= 9 && quality.entropy >= 2.2;
}

async function calibrateScene(scene, tiles) {
  const values = [];
  await mapLimit(calibrationTiles(tiles), Math.min(8, concurrency), async ({ z, x, y }) => {
    const tile = await fetchTile(scene, z, x, y);
    if (tile && isInformativeTile(tile)) sampleLuminance(tile, values);
  });

  if (values.length < 1000) {
    return { low: 4, high: 244, samples: values.length, fallback: true };
  }

  const sorted = values.sort((left, right) => left - right);
  const low = percentile(sorted, 0.015);
  const high = percentile(sorted, 0.985);
  return { low, high, samples: values.length, fallback: false };
}

function enhanceTile(bytes, calibration) {
  const image = jpeg.decode(bytes, { useTArray: true, maxMemoryUsageInMB: 512 });
  const { width, height, data } = image;
  const pixels = width * height;
  const { low, high } = calibration;
  const scale = high > low + 18 ? 255 / (high - low) : 1;
  const contrast = high > low + 18 ? 1.04 : 1;
  const gamma = 0.96;

  const red = new Float32Array(pixels);
  const green = new Float32Array(pixels);
  const blue = new Float32Array(pixels);
  for (let pixel = 0, offset = 0; pixel < pixels; pixel += 1, offset += 4) {
    red[pixel] = data[offset];
    green[pixel] = data[offset + 1];
    blue[pixel] = data[offset + 2];
  }

  const redBlur = blurChannel(red, width, height);
  const greenBlur = blurChannel(green, width, height);
  const blueBlur = blurChannel(blue, width, height);
  const output = Buffer.alloc(data.length);
  const sharpen = 0.34;
  const saturation = 1.06;

  for (let pixel = 0, offset = 0; pixel < pixels; pixel += 1, offset += 4) {
    const channels = [
      red[pixel] + (red[pixel] - redBlur[pixel]) * sharpen,
      green[pixel] + (green[pixel] - greenBlur[pixel]) * sharpen,
      blue[pixel] + (blue[pixel] - blueBlur[pixel]) * sharpen
    ];

    let adjustedLuma = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    adjustedLuma = ((adjustedLuma - low) * scale - 127.5) * contrast + 127.5;
    adjustedLuma = 255 * (Math.max(0, Math.min(255, adjustedLuma)) / 255) ** gamma;

    const originalLuma = Math.max(1, 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]);
    const ratio = adjustedLuma / originalLuma;
    const scaled = channels.map((channel) => channel * ratio);
    const scaledLuma = 0.2126 * scaled[0] + 0.7152 * scaled[1] + 0.0722 * scaled[2];

    output[offset] = clamp(scaledLuma + (scaled[0] - scaledLuma) * saturation);
    output[offset + 1] = clamp(scaledLuma + (scaled[1] - scaledLuma) * saturation);
    output[offset + 2] = clamp(scaledLuma + (scaled[2] - scaledLuma) * saturation);
    output[offset + 3] = 255;
  }

  return jpeg.encode({ data: output, width, height }, jpegQuality).data;
}

function tilesForBounds(bounds, zoom) {
  const minX = lonToTile(bounds.west, zoom);
  const maxX = lonToTile(bounds.east, zoom);
  const minY = latToTile(bounds.north, zoom);
  const maxY = latToTile(bounds.south, zoom);
  const tiles = [];
  for (let x = minX; x <= maxX; x += 1) {
    for (let y = minY; y <= maxY; y += 1) {
      tiles.push({ z: zoom, x, y });
    }
  }
  return tiles;
}

async function tilesForHotspots(zoom) {
  const bytes = await readFile(hotspotPath, 'utf8');
  const index = JSON.parse(bytes);
  const hotspots = Array.isArray(index.hotspots) ? index.hotspots : [];
  if (!hotspots.length) {
    throw new Error(`No hotspots found in ${hotspotPath}`);
  }

  const unique = new Map();
  for (const hotspot of hotspots) {
    if (!Number.isFinite(hotspot.lng) || !Number.isFinite(hotspot.lat)) continue;
    const centerX = lonToTile(hotspot.lng, zoom);
    const centerY = latToTile(hotspot.lat, zoom);
    for (let x = centerX - hotspotTileRadius; x <= centerX + hotspotTileRadius; x += 1) {
      for (let y = centerY - hotspotTileRadius; y <= centerY + hotspotTileRadius; y += 1) {
        unique.set(`${zoom}/${x}/${y}`, { z: zoom, x, y });
      }
    }
  }

  return [...unique.values()];
}

function boundsForTiles(tiles) {
  if (!tiles.length) return enhancedBounds;
  return tiles.reduce(
    (bounds, { z, x, y }) => ({
      west: Math.min(bounds.west, tileToLon(x, z)),
      south: Math.min(bounds.south, tileToLat(y + 1, z)),
      east: Math.max(bounds.east, tileToLon(x + 1, z)),
      north: Math.max(bounds.north, tileToLat(y, z))
    }),
    { west: Infinity, south: Infinity, east: -Infinity, north: -Infinity }
  );
}

async function mapLimit(items, limit, worker) {
  let index = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (index < items.length) {
      const item = items[index];
      index += 1;
      await worker(item);
    }
  });
  await Promise.all(runners);
}

if (!zoomLevels.length) {
  throw new Error('No valid ENHANCED_TILE_ZOOMS were provided');
}

if (enhancedBounds.west >= enhancedBounds.east || enhancedBounds.south >= enhancedBounds.north) {
  throw new Error('Enhanced imagery bounds do not intersect');
}

if (cleanOutput) {
  await rm(outputRoot, { recursive: true, force: true });
}

const startedAt = new Date().toISOString();
const sceneTiles = tileMode === 'hotspots'
  ? (await Promise.all(zoomLevels.map((zoom) => tilesForHotspots(zoom)))).flat()
  : zoomLevels.flatMap((zoom) => tilesForBounds(enhancedBounds, zoom));
const selectedSceneTiles = smokeLimit > 0 ? sceneTiles.slice(0, smokeLimit) : sceneTiles;
const manifestBounds = tileMode === 'hotspots' ? boundsForTiles(selectedSceneTiles) : enhancedBounds;
const manifest = {
  generatedAt: startedAt,
  bounds: manifestBounds,
  zoomLevels,
  tilePixelSize: 512,
  selection: {
    mode: tileMode,
    hotspotTileRadius: tileMode === 'hotspots' ? hotspotTileRadius : null,
    hotspots: tileMode === 'hotspots' ? hotspotInputPath : null
  },
  source: scenes,
  method: {
    type: 'deterministic-retina-enhancement',
    generative: false,
    operations: ['512px source tile fetch', 'scene-sampled percentile luminance stretch', 'mild unsharp mask', 'mild saturation lift'],
    note: 'No diffusion, GAN, or learned texture synthesis is used. Output is for visual inspection and preserves the raw Vantor COG fallback.'
  },
  counts: {}
};

let totalWritten = 0;
for (const [sceneKey, scene] of Object.entries(scenes)) {
  const selectedTiles = selectedSceneTiles;
  const calibration = await calibrateScene(scene, selectedTiles);
  let written = 0;
  let skipped = 0;

  await mapLimit(selectedTiles, concurrency, async ({ z, x, y }) => {
    const tile = await fetchTile(scene, z, x, y);
    if (!tile || !isInformativeTile(tile)) {
      skipped += 1;
      return;
    }

    const enhanced = enhanceTile(tile, calibration);
    const outputPath = resolve(outputRoot, sceneKey, String(z), String(x), `${y}.jpg`);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, enhanced.length > 100 ? enhanced : transparentJpeg);
    written += 1;
  });

  manifest.counts[sceneKey] = { requested: selectedTiles.length, written, skipped, calibration };
  totalWritten += written;
  console.log(`${sceneKey}: wrote ${written}/${selectedTiles.length} enhanced tiles (${skipped} skipped)`);
}

await mkdir(outputRoot, { recursive: true });
await writeFile(resolve(outputRoot, 'manifest.json'), JSON.stringify(manifest, null, 2));
console.log(`Generated ${totalWritten} enhanced satellite tiles in ${outputRoot}`);
