import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import jpeg from 'jpeg-js';

const zoom = 14;
const bounds = {
  west: -67.14,
  south: 10.54,
  east: -66.96,
  north: 10.65
};
const fallbackJpeg = Buffer.from(
  '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Aqf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2gAMAwEAAgADAAAAEP/EFBQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EFBQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EFBABAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAT8QH//Z',
  'base64'
);

const scenes = {
  before: [
    'https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/sentinel-2-c1-l2a/19/P/GM/2026/6/S2A_T19PGM_20260622T150938_L2A/TCI.tif',
    'https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/sentinel-2-c1-l2a/19/P/FM/2026/6/S2A_T19PFM_20260622T150938_L2A/TCI.tif'
  ],
  after: [
    'https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/sentinel-2-c1-l2a/19/P/GM/2026/6/S2C_T19PGM_20260627T145723_L2A/TCI.tif',
    'https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/sentinel-2-c1-l2a/19/P/FM/2026/6/S2C_T19PFM_20260627T145723_L2A/TCI.tif'
  ]
};

function lonToTile(lon, z) {
  return Math.floor(((lon + 180) / 360) * 2 ** z);
}

function latToTile(lat, z) {
  const radians = (lat * Math.PI) / 180;
  return Math.floor(((1 - Math.log(Math.tan(radians) + 1 / Math.cos(radians)) / Math.PI) / 2) * 2 ** z);
}

function titilerTileUrl(cogUrl, z, x, y) {
  const encodedCog = encodeURIComponent(cogUrl);
  return `https://titiler.xyz/cog/tiles/WebMercatorQuad/${z}/${x}/${y}.jpg?url=${encodedCog}`;
}

async function fetchTile(cogUrl, z, x, y) {
  const response = await fetch(titilerTileUrl(cogUrl, z, x, y), {
    headers: { accept: 'image/jpeg,*/*;q=0.8' }
  });
  if (!response.ok) return null;

  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('image')) return null;

  const bytes = Buffer.from(await response.arrayBuffer());
  return bytes.length > 100 ? bytes : null;
}

function scoreTile(bytes) {
  try {
    const image = jpeg.decode(bytes, { useTArray: true, maxMemoryUsageInMB: 256 });
    const data = image.data;
    let veryDark = 0;
    let saturatedWhite = 0;
    let luminanceSum = 0;
    let luminanceSquaredSum = 0;
    const pixels = image.width * image.height;

    for (let index = 0; index < data.length; index += 4) {
      const red = data[index];
      const green = data[index + 1];
      const blue = data[index + 2];
      const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;
      luminanceSum += luminance;
      luminanceSquaredSum += luminance * luminance;
      if (luminance < 10) veryDark += 1;
      if (red > 245 && green > 245 && blue > 245) saturatedWhite += 1;
    }

    const mean = luminanceSum / pixels;
    const variance = Math.max(0, luminanceSquaredSum / pixels - mean * mean);
    const veryDarkRatio = veryDark / pixels;
    const saturatedWhiteRatio = saturatedWhite / pixels;
    return variance + mean * 0.8 - veryDarkRatio * 260 - saturatedWhiteRatio * 80;
  } catch {
    return -Infinity;
  }
}

async function fetchBestTile(cogUrls, z, x, y) {
  const candidates = [];
  for (const cogUrl of cogUrls) {
    const tile = await fetchTile(cogUrl, z, x, y);
    if (tile) candidates.push({ tile, score: scoreTile(tile) });
  }

  candidates.sort((left, right) => right.score - left.score);
  return candidates[0]?.tile || null;
}

const minX = lonToTile(bounds.west, zoom);
const maxX = lonToTile(bounds.east, zoom);
const minY = latToTile(bounds.north, zoom);
const maxY = latToTile(bounds.south, zoom);
const totalTiles = (maxX - minX + 1) * (maxY - minY + 1);

for (const [scene, cogs] of Object.entries(scenes)) {
  let cached = 0;
  let transparent = 0;

  for (let x = minX; x <= maxX; x += 1) {
    for (let y = minY; y <= maxY; y += 1) {
      let tile = await fetchBestTile(cogs, zoom, x, y);

      if (!tile) {
        tile = fallbackJpeg;
        transparent += 1;
      }

      const outputPath = resolve(`public/data/sentinel-tiles/${scene}/${zoom}/${x}/${y}.jpg`);
      await mkdir(dirname(outputPath), { recursive: true });
      await writeFile(outputPath, tile);
      cached += 1;
    }
  }

  console.log(`Cached ${cached}/${totalTiles} ${scene} tiles (${transparent} transparent fallbacks)`);
}
