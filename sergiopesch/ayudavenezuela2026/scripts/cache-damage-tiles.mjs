import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { spawn } from 'node:child_process';

const zoomLevels = [14, 15, 16, 17, 18];
const bounds = {
  west: -67.14,
  south: 10.54,
  east: -66.96,
  north: 10.65
};
const tileRoot = resolve('public/data/damage-tiles');
const sourcePath = resolve('public/data/microsoft-damage-catia-lite.geojson');
const severityStyle = {
  high: { color: '#b42318', fillOpacity: 0.72, strokeOpacity: 0.9, strokeWidth: 1.1 },
  moderate: { color: '#f97316', fillOpacity: 0.68, strokeOpacity: 0.86, strokeWidth: 1 },
  observed: { color: '#facc15', fillOpacity: 0.58, strokeOpacity: 0.84, strokeWidth: 0.9 },
  uncertain: { color: '#64748b', fillOpacity: 0.56, strokeOpacity: 0.8, strokeWidth: 0.9 }
};

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
  const n = Math.PI - (2 * Math.PI * y) / 2 ** z;
  return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
}

function project(lon, lat, z) {
  const scale = 256 * 2 ** z;
  const sin = Math.sin((lat * Math.PI) / 180);
  return [
    ((lon + 180) / 360) * scale,
    (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale
  ];
}

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

function featureBBox(feature) {
  const pairs = coordinatePairs(feature.geometry);
  return pairs.reduce(
    (bbox, [lon, lat]) => ({
      west: Math.min(bbox.west, lon),
      south: Math.min(bbox.south, lat),
      east: Math.max(bbox.east, lon),
      north: Math.max(bbox.north, lat)
    }),
    { west: Infinity, south: Infinity, east: -Infinity, north: -Infinity }
  );
}

function intersects(a, b) {
  return a.west <= b.east && a.east >= b.west && a.south <= b.north && a.north >= b.south;
}

function pathForRing(ring, tileOriginX, tileOriginY, zoom) {
  return ring
    .map(([lon, lat], index) => {
      const [worldX, worldY] = project(lon, lat, zoom);
      const x = Math.round((worldX - tileOriginX) * 10) / 10;
      const y = Math.round((worldY - tileOriginY) * 10) / 10;
      return `${index ? 'L' : 'M'}${x} ${y}`;
    })
    .join(' ');
}

function pathForFeature(feature, tileOriginX, tileOriginY, zoom) {
  if (feature.geometry.type === 'Polygon') {
    return feature.geometry.coordinates.map((ring) => `${pathForRing(ring, tileOriginX, tileOriginY, zoom)} Z`).join(' ');
  }

  return feature.geometry.coordinates
    .flatMap((polygon) => polygon.map((ring) => `${pathForRing(ring, tileOriginX, tileOriginY, zoom)} Z`))
    .join(' ');
}

function convertSvgToPng(svg, outputPath) {
  return new Promise((resolveConvert, rejectConvert) => {
    const convert = spawn('convert', ['-background', 'none', 'svg:-', '-define', 'png:compression-level=9', 'png32:' + outputPath]);
    const stderr = [];

    convert.stderr.on('data', (chunk) => stderr.push(chunk));
    convert.on('error', rejectConvert);
    convert.on('close', (code) => {
      if (code === 0) {
        resolveConvert();
        return;
      }
      rejectConvert(new Error(`ImageMagick convert failed (${code}): ${Buffer.concat(stderr).toString('utf8')}`));
    });
    convert.stdin.end(svg);
  });
}

const source = JSON.parse(await readFile(sourcePath, 'utf8'));
const features = source.features.map((feature) => ({ ...feature, bbox: featureBBox(feature) }));

await rm(tileRoot, { recursive: true, force: true });

let tileCount = 0;
for (const zoom of zoomLevels) {
  const minX = lonToTile(bounds.west, zoom);
  const maxX = lonToTile(bounds.east, zoom);
  const minY = latToTile(bounds.north, zoom);
  const maxY = latToTile(bounds.south, zoom);

  for (let x = minX; x <= maxX; x += 1) {
    for (let y = minY; y <= maxY; y += 1) {
      const tileBounds = {
        west: tileToLon(x, zoom),
        east: tileToLon(x + 1, zoom),
        north: tileToLat(y, zoom),
        south: tileToLat(y + 1, zoom)
      };
      const tileFeatures = features.filter((feature) => intersects(feature.bbox, tileBounds));
      if (!tileFeatures.length) continue;

      const tileOriginX = x * 256;
      const tileOriginY = y * 256;
      const paths = tileFeatures
        .map((feature) => {
          const style = severityStyle[feature.properties.severity] || severityStyle.observed;
          const path = pathForFeature(feature, tileOriginX, tileOriginY, zoom);
          const strokeWidth = Math.max(style.strokeWidth * (zoom >= 17 ? 1.3 : 1), 1);
          return `<path d="${path}" fill="${style.color}" fill-opacity="${style.fillOpacity}" stroke="${style.color}" stroke-opacity="${style.strokeOpacity}" stroke-width="${strokeWidth}" vector-effect="non-scaling-stroke" fill-rule="evenodd"/>`;
        })
        .join('');
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">${paths}</svg>`;
      const outputPath = resolve(tileRoot, String(zoom), String(x), `${y}.png`);
      await mkdir(dirname(outputPath), { recursive: true });
      await writeFile(`${outputPath}.svg`, svg);
      await convertSvgToPng(svg, outputPath);
      await rm(`${outputPath}.svg`);
      tileCount += 1;
    }
  }
}

console.log(`Cached ${tileCount} damage overlay tiles for zooms ${zoomLevels.join(', ')} in ${tileRoot}`);
