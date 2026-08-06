import { chromium } from 'playwright';
import { existsSync, readdirSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import { inflateSync } from 'node:zlib';

const appUrl = process.env.QA_URL || 'http://localhost:5173/';
const outputDir = process.env.QA_OUTPUT_DIR || '/tmp/ayuda-imagery-qa';
function cachedPlaywrightChromiumExecutable() {
  const cacheDir = `${process.env.HOME || ''}/Library/Caches/ms-playwright`;
  if (!existsSync(cacheDir)) return undefined;

  return readdirSync(cacheDir)
    .filter((entry) => entry.startsWith('chromium_headless_shell-'))
    .sort()
    .reverse()
    .map((entry) => `${cacheDir}/${entry}/chrome-headless-shell-mac-arm64/chrome-headless-shell`)
    .find((path) => existsSync(path));
}

const chromiumExecutablePath =
  process.env.CHROMIUM_EXECUTABLE_PATH ||
  cachedPlaywrightChromiumExecutable() ||
  [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
  ].find((path) => existsSync(path));

const thresholds = {
  comparisonReadyMs: 45000,
  minTilesRendered: 16,
  minTileNaturalWidth: 512,
  minStddev: 21,
  minEntropy: 1.0,
  minGradient: 2.5,
  minLaplacian: 3,
  maxDarkRatio: 0.9,
  maxWhiteRatio: 0.55,
  minFullMeanAbsDiff: 5,
  minFullChangedRatio: 0.045,
  minSideChangedRatio: 0.025,
  minDamageColorRatio: 0.008,
  minDamageColorDelta: 0.01
};

function assertMetric(condition, message, details) {
  if (!condition) {
    const suffix = details ? ` ${JSON.stringify(details)}` : '';
    throw new Error(`${message}${suffix}`);
  }
}

function parsePng(buffer) {
  if (buffer.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') {
    throw new Error('Screenshot was not a PNG');
  }

  let position = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  let interlace = 0;
  const idatChunks = [];

  while (position < buffer.length) {
    const length = buffer.readUInt32BE(position);
    position += 4;
    const type = buffer.subarray(position, position + 4).toString('ascii');
    position += 4;
    const data = buffer.subarray(position, position + length);
    position += length + 4;

    if (type === 'IHDR') {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
      interlace = data[12];
    } else if (type === 'IDAT') {
      idatChunks.push(data);
    } else if (type === 'IEND') {
      break;
    }
  }

  const sourceBytesPerPixel = colorType === 6 ? 4 : colorType === 2 ? 3 : 0;
  if (bitDepth !== 8 || !sourceBytesPerPixel || interlace !== 0) {
    throw new Error(`Unsupported screenshot PNG format ${bitDepth}/${colorType}/${interlace}`);
  }

  const sourceStride = width * sourceBytesPerPixel;
  const raw = inflateSync(Buffer.concat(idatChunks));
  const rgba = Buffer.alloc(width * height * 4);
  const previous = Buffer.alloc(sourceStride);
  const row = Buffer.alloc(sourceStride);
  let inputPosition = 0;
  let outputPosition = 0;

  for (let y = 0; y < height; y += 1) {
    const filter = raw[inputPosition];
    inputPosition += 1;

    for (let x = 0; x < sourceStride; x += 1) {
      const value = raw[inputPosition];
      inputPosition += 1;
      const left = x >= sourceBytesPerPixel ? row[x - sourceBytesPerPixel] : 0;
      const up = previous[x];
      const upLeft = x >= sourceBytesPerPixel ? previous[x - sourceBytesPerPixel] : 0;
      let reconstructed;

      if (filter === 0) reconstructed = value;
      else if (filter === 1) reconstructed = value + left;
      else if (filter === 2) reconstructed = value + up;
      else if (filter === 3) reconstructed = value + Math.floor((left + up) / 2);
      else if (filter === 4) {
        const p = left + up - upLeft;
        const pa = Math.abs(p - left);
        const pb = Math.abs(p - up);
        const pc = Math.abs(p - upLeft);
        reconstructed = value + (pa <= pb && pa <= pc ? left : pb <= pc ? up : upLeft);
      } else {
        throw new Error(`Unsupported PNG row filter ${filter}`);
      }

      row[x] = reconstructed & 255;
    }

    for (let x = 0; x < width; x += 1) {
      const sourceIndex = x * sourceBytesPerPixel;
      const outputIndex = outputPosition + x * 4;
      rgba[outputIndex] = row[sourceIndex];
      rgba[outputIndex + 1] = row[sourceIndex + 1];
      rgba[outputIndex + 2] = row[sourceIndex + 2];
      rgba[outputIndex + 3] = sourceBytesPerPixel === 4 ? row[sourceIndex + 3] : 255;
    }

    row.copy(previous);
    outputPosition += width * 4;
  }

  return { width, height, rgba };
}

function luminanceAt(image, x, y) {
  const index = (y * image.width + x) * 4;
  return 0.2126 * image.rgba[index] + 0.7152 * image.rgba[index + 1] + 0.0722 * image.rgba[index + 2];
}

function imageMetrics(image, crop = { x0: 0, y0: 0, x1: image.width, y1: image.height }) {
  const x0 = Math.max(1, Math.floor(crop.x0));
  const y0 = Math.max(1, Math.floor(crop.y0));
  const x1 = Math.min(image.width - 1, Math.floor(crop.x1));
  const y1 = Math.min(image.height - 1, Math.floor(crop.y1));
  const histogram = new Array(32).fill(0);
  let count = 0;
  let sum = 0;
  let sumSquared = 0;
  let dark = 0;
  let white = 0;
  let gradient = 0;
  let laplacian = 0;

  for (let y = y0; y < y1; y += 1) {
    for (let x = x0; x < x1; x += 1) {
      const index = (y * image.width + x) * 4;
      const red = image.rgba[index];
      const green = image.rgba[index + 1];
      const blue = image.rgba[index + 2];
      const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;

      count += 1;
      sum += luminance;
      sumSquared += luminance * luminance;
      if (luminance < 12) dark += 1;
      if (red > 245 && green > 245 && blue > 245) white += 1;
      gradient += Math.abs(luminance - luminanceAt(image, x - 1, y));
      gradient += Math.abs(luminance - luminanceAt(image, x, y - 1));
      laplacian += Math.abs(
        4 * luminance -
          luminanceAt(image, x - 1, y) -
          luminanceAt(image, x + 1, y) -
          luminanceAt(image, x, y - 1) -
          luminanceAt(image, x, y + 1)
      );
      histogram[Math.max(0, Math.min(31, Math.floor(luminance / 8)))] += 1;
    }
  }

  let entropy = 0;
  for (const bucket of histogram) {
    if (!bucket) continue;
    const probability = bucket / count;
    entropy -= probability * Math.log2(probability);
  }

  const mean = sum / count;
  return {
    mean,
    stddev: Math.sqrt(Math.max(0, sumSquared / count - mean * mean)),
    entropy,
    gradient: gradient / count,
    laplacian: laplacian / count,
    darkRatio: dark / count,
    whiteRatio: white / count
  };
}

function diffMetrics(left, right, crop = { x0: 0, y0: 0, x1: left.width, y1: left.height }) {
  const x0 = Math.max(0, Math.floor(crop.x0));
  const y0 = Math.max(0, Math.floor(crop.y0));
  const x1 = Math.min(left.width, Math.floor(crop.x1));
  const y1 = Math.min(left.height, Math.floor(crop.y1));
  let count = 0;
  let sum = 0;
  let changed = 0;

  for (let y = y0; y < y1; y += 1) {
    for (let x = x0; x < x1; x += 1) {
      const index = (y * left.width + x) * 4;
      const delta =
        (Math.abs(left.rgba[index] - right.rgba[index]) +
          Math.abs(left.rgba[index + 1] - right.rgba[index + 1]) +
          Math.abs(left.rgba[index + 2] - right.rgba[index + 2])) /
        3;
      count += 1;
      sum += delta;
      if (delta > 20) changed += 1;
    }
  }

  return {
    meanAbsDiff: sum / count,
    changedRatio: changed / count
  };
}

function damageColorMetrics(image, crop = { x0: 0, y0: 0, x1: image.width, y1: image.height }) {
  const x0 = Math.max(0, Math.floor(crop.x0));
  const y0 = Math.max(0, Math.floor(crop.y0));
  const x1 = Math.min(image.width, Math.floor(crop.x1));
  const y1 = Math.min(image.height, Math.floor(crop.y1));
  let count = 0;
  let damageColored = 0;

  for (let y = y0; y < y1; y += 1) {
    for (let x = x0; x < x1; x += 1) {
      const index = (y * image.width + x) * 4;
      const red = image.rgba[index];
      const green = image.rgba[index + 1];
      const blue = image.rgba[index + 2];
      const warmDamage = red > 145 && red > green * 1.08 && red > blue * 1.05 && green < 175;
      const magentaDamage = red > 135 && blue > 110 && red > green * 1.15 && blue > green * 1.05;

      count += 1;
      if (warmDamage || magentaDamage) damageColored += 1;
    }
  }

  return {
    damageColorRatio: damageColored / count,
    damageColored,
    count
  };
}

function assertImageQuality(label, metrics) {
  assertMetric(metrics.stddev > thresholds.minStddev, `${label} has low contrast / may be blank`, metrics);
  assertMetric(metrics.entropy > thresholds.minEntropy, `${label} has low entropy / may be flat`, metrics);
  assertMetric(metrics.gradient > thresholds.minGradient, `${label} is too soft`, metrics);
  assertMetric(metrics.laplacian > thresholds.minLaplacian, `${label} lacks edge detail`, metrics);
  assertMetric(
    metrics.darkRatio < thresholds.maxDarkRatio && metrics.whiteRatio < thresholds.maxWhiteRatio,
    `${label} is dominated by blank, dark, cloud, or white pixels`,
    metrics
  );
}

async function setSlider(page, slider, target) {
  await slider.focus();
  for (let attempts = 0; attempts < 80; attempts += 1) {
    const current = Number(await slider.getAttribute('aria-valuenow'));
    if (current === target) return;
    await page.keyboard.press(current > target ? 'ArrowLeft' : 'ArrowRight');
  }

  throw new Error(`Slider failed to reach ${target}, got ${await slider.getAttribute('aria-valuenow')}`);
}

async function hiddenMapScreenshot(page, slider, clip, target, filename) {
  await setSlider(page, slider, target);
  await page.waitForFunction(
    (expected) => Math.abs(Number(document.querySelector('.comparison-control')?.getAttribute('aria-valuenow')) - expected) < 0.1,
    target
  );
  await waitForComparisonTiles(page, `imagery screenshot ${target}`);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await assertComparisonAlignment(page, `imagery screenshot ${target}`);

  const style = await page.addStyleTag({
    content:
      '.comparison-divider,.comparison-control,.comparison-context,.comparison-side-labels,.damage-legend,.map-status,.map-toolbar,.mobile-map-controls{visibility:hidden!important}'
  });
  const screenshot = await page.screenshot({ clip, path: `${outputDir}/${filename}` });
  await style.evaluate((element) => element.remove());
  return screenshot;
}

async function hiddenCurrentMapScreenshot(page, clip, filename) {
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const style = await page.addStyleTag({
    content:
      '.comparison-divider,.comparison-control,.comparison-context,.comparison-side-labels,.damage-legend,.map-status,.map-toolbar,.mobile-map-controls,.worst-experience-panel{visibility:hidden!important}'
  });
  const screenshot = await page.screenshot({ clip, path: `${outputDir}/${filename}` });
  await style.evaluate((element) => element.remove());
  return screenshot;
}

async function assertComparisonAlignment(page, label) {
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const metrics = await page.evaluate(() => {
    const rect = (element) => {
      const box = element?.getBoundingClientRect();
      return box ? { left: box.left, right: box.right, width: box.width } : null;
    };
    const slider = document.querySelector('.comparison-control');
    const canvas = rect(document.querySelector('.map-canvas'));
    const mapPane = rect(document.querySelector('.leaflet-map-pane'));
    const divider = rect(document.querySelector('.comparison-divider'));
    const grip = rect(document.querySelector('.comparison-grip'));
    const beforeLayer = document.querySelector('.comparison-before-tile-layer');
    const afterLayer = document.querySelector('.comparison-after-tile-layer');
    const damageLayer = document.querySelector('.comparison-damage-raster-layer');
    const value = Number(slider?.getAttribute('aria-valuenow') || 0);
    const splitX = canvas ? canvas.left + canvas.width * (value / 100) : 0;
    const clip = (layer) => (layer ? getComputedStyle(layer).clip : '');
    const parseRect = (value) => {
      const match = value.match(/rect\(([^)]+)\)/);
      if (!match) return null;
      const parts = match[1].trim().split(/[,\s]+/).filter(Boolean).map((part) => Number.parseFloat(part));
      if (parts.some((part) => Number.isNaN(part))) return null;
      const [top, right, bottom, left] = parts;
      return { top, right, bottom, left };
    };
    const beforeRect = rect(beforeLayer);
    const afterRect = rect(afterLayer);
    const damageRect = rect(damageLayer);
    const beforeRectClip = parseRect(clip(beforeLayer));
    const afterRectClip = parseRect(clip(afterLayer));
    const damageRectClip = parseRect(clip(damageLayer));

    return {
      value,
      splitX,
      dividerCenter: divider ? divider.left + divider.width / 2 : null,
      gripCenter: grip ? grip.left + grip.width / 2 : null,
      beforeClip: clip(beforeLayer),
      afterClip: clip(afterLayer),
      damageClip: clip(damageLayer),
      beforeBoundary: mapPane && beforeRect && beforeRectClip ? mapPane.left + beforeRectClip.right : null,
      afterBoundary: mapPane && afterRect && afterRectClip ? mapPane.left + afterRectClip.left : null,
      damageBoundary: mapPane && damageRect && damageRectClip ? mapPane.left + damageRectClip.left : null,
      hasDamageLayer: Boolean(damageLayer),
      damageTiles: document.querySelectorAll('.comparison-damage-raster-layer img').length
    };
  });

  assertMetric(Math.abs(metrics.dividerCenter - metrics.splitX) <= 1.5, `${label}: divider is not aligned to split`, metrics);
  assertMetric(Math.abs(metrics.gripCenter - metrics.splitX) <= 1.5, `${label}: grip is not aligned to split`, metrics);
  assertMetric(metrics.beforeClip.includes('rect') && metrics.afterClip.includes('rect'), `${label}: comparison layers should use rect pixel clips`, metrics);
  assertMetric(Math.abs(metrics.beforeBoundary - metrics.splitX) <= 1.5, `${label}: before layer clip boundary is not aligned`, metrics);
  assertMetric(Math.abs(metrics.afterBoundary - metrics.splitX) <= 1.5, `${label}: after layer clip boundary is not aligned`, metrics);
  if (metrics.hasDamageLayer && metrics.damageTiles > 0) {
    assertMetric(metrics.damageClip === metrics.afterClip, `${label}: damage layer should share after-side clipping`, metrics);
    assertMetric(Math.abs(metrics.damageBoundary - metrics.splitX) <= 1.5, `${label}: damage layer clip boundary is not aligned`, metrics);
  }
}

async function waitForComparisonTiles(page, label) {
  await page.waitForFunction(
    (minTileNaturalWidth) => {
      const mapRect = document.querySelector('.map-canvas')?.getBoundingClientRect();
      if (!mapRect) return false;
      const beforeImages = [...document.querySelectorAll('.comparison-before-tile-layer img')];
      const afterImages = [...document.querySelectorAll('.comparison-after-tile-layer img')];
      const loaded = (image) => image.complete && image.naturalWidth >= minTileNaturalWidth && image.naturalHeight >= minTileNaturalWidth;
      const visible = (image) => {
        const rect = image.getBoundingClientRect();
        return rect.right > mapRect.left && rect.left < mapRect.right && rect.bottom > mapRect.top && rect.top < mapRect.bottom;
      };
      const visibleBefore = beforeImages.filter(visible);
      const visibleAfter = afterImages.filter(visible);
      return visibleBefore.length >= 4 &&
        visibleAfter.length >= 4 &&
        visibleBefore.every(loaded) &&
        visibleAfter.every(loaded);
    },
    thresholds.minTileNaturalWidth,
    { timeout: thresholds.comparisonReadyMs }
  ).catch((error) => {
    throw new Error(`${label}: before/after Vantor tiles did not load: ${error.message}`);
  });
}

async function assertWorstAreaImagery(page, clip, rank) {
  await waitForComparisonTiles(page, `worst area ${rank}`);
  await page.waitForTimeout(3000);
  await waitForComparisonTiles(page, `worst area ${rank} settled`);
  await assertComparisonAlignment(page, `worst area ${rank}`);

  const state = await page.evaluate(() => {
    const urls = [
      ...performance.getEntriesByType('resource').map((entry) => entry.name),
      ...[...document.querySelectorAll('.comparison-before-tile-layer img,.comparison-after-tile-layer img')].map(
        (image) => image.currentSrc
      )
    ];

    return {
      beforeImageCount: document.querySelectorAll('.comparison-before-tile-layer img').length,
      afterImageCount: document.querySelectorAll('.comparison-after-tile-layer img').length,
      preEventVantorTileCount: urls.filter((name) => name.includes('B120001100513B10.tif')).length,
      postEventVantorTileCount: urls.filter((name) => name.includes('B15000110186C610.tif')).length,
      localEnhancedTileCount: urls.filter((name) => name.includes('/data/enhanced-satellite-tiles/')).length,
      localEnhancedVisibleCount: [
        ...document.querySelectorAll('.comparison-before-enhanced-tile-layer img,.comparison-after-enhanced-tile-layer img')
      ].filter((image) => image.complete && image.naturalWidth >= 512 && image.naturalHeight >= 512).length
    };
  });

  assertMetric(
    state.beforeImageCount >= 4 &&
      state.afterImageCount >= 4 &&
      state.preEventVantorTileCount > 0 &&
      state.postEventVantorTileCount > 0 &&
      state.localEnhancedTileCount === 0 &&
      state.localEnhancedVisibleCount === 0,
    `Affected area ${rank} should render canonical 2x Vantor STAC tiles without local enhanced overlay`,
    state
  );

  const screenshot = await hiddenCurrentMapScreenshot(page, clip, `worst-area-${rank}-raw-vantor.png`);
  const image = parsePng(screenshot);
  const metrics = imageMetrics(image, {
    x0: image.width * 0.12,
    y0: image.height * 0.12,
    x1: image.width * 0.88,
    y1: image.height * 0.88
  });
  assertMetric(
    metrics.stddev > 20 &&
      metrics.entropy > 3 &&
      metrics.gradient > thresholds.minGradient &&
      metrics.darkRatio < 0.08 &&
      metrics.whiteRatio < 0.08,
    `Affected area ${rank} raw Vantor image has blank, black, or flat tile artifacts`,
    metrics
  );

  return { ...state, metrics, screenshot: `${outputDir}/worst-area-${rank}-raw-vantor.png` };
}

async function clickButtonContaining(page, labels, description) {
  const clicked = await page.evaluate((buttonLabels) => {
    const normalizedLabels = buttonLabels.map((label) => label.toLowerCase());
    const button = [...document.querySelectorAll('button')].find((candidate) => {
      const text = candidate.textContent?.toLowerCase() || '';
      const aria = candidate.getAttribute('aria-label')?.toLowerCase() || '';
      return normalizedLabels.some((label) => text.includes(label) || aria.includes(label));
    });

    if (!(button instanceof HTMLButtonElement)) return false;
    button.click();
    return true;
  }, labels);

  if (!clicked) {
    const buttons = await page.evaluate(() =>
      [...document.querySelectorAll('button')]
        .map((button) => button.textContent?.trim() || button.getAttribute('aria-label') || '')
        .filter(Boolean)
    );
    throw new Error(`${description} button was not found. Buttons: ${buttons.join(' | ')}`);
  }
}

async function main() {
  await mkdir(outputDir, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(chromiumExecutablePath ? { executablePath: chromiumExecutablePath } : {})
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
  const consoleIssues = [];

  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type()) && !message.text().includes('404')) {
      consoleIssues.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on('pageerror', (error) => consoleIssues.push(`pageerror: ${error.message}`));
  await page.route('https://nominatim.openstreetmap.org/search**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        {
          place_id: 26062027,
          osm_type: 'node',
          osm_id: 424243,
          display_name: 'Catia La Mar, Municipio Vargas, La Guaira, Venezuela',
          lat: '10.592425',
          lon: '-67.007108',
          type: 'town',
          class: 'place',
          importance: 0.78,
          boundingbox: ['10.592325', '10.592525', '-67.007208', '-67.007008'],
          address: {
            town: 'Catia La Mar',
            state: 'La Guaira',
            country: 'Venezuela'
          }
        }
      ])
    });
  });

  await page.goto(appUrl, { waitUntil: 'domcontentloaded' });
  await page.locator('button').first().waitFor({ timeout: 30000 });
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll('button')].some((button) => button.textContent?.includes('English')) ||
      Boolean(document.querySelector('input[aria-label="Search address or place in Venezuela"]')),
    null,
    { timeout: 30000 }
  );
  await page.evaluate(() => {
    const englishButton = [...document.querySelectorAll('button')].find((button) =>
      button.textContent?.includes('English')
    );
    if (englishButton instanceof HTMLButtonElement) {
      englishButton.click();
      return;
    }
    if (document.querySelector('input[aria-label="Search address or place in Venezuela"]')) return;
    throw new Error(
      `English language button was not found. Buttons: ${[...document.querySelectorAll('button')]
        .map((button) => button.textContent?.trim())
        .filter(Boolean)
        .join(' | ')}`
    );
  });
  await page.waitForFunction(() => document.querySelector('.map-canvas.leaflet-container'));

  const initialResources = await page.evaluate(() => performance.getEntriesByType('resource').map((entry) => entry.name));
  assertMetric(
    !initialResources.some((name) => name.includes('tiles.openaerialmap.org')),
    'Vantor comparison tiles should wait until the map is over sourced imagery bounds'
  );
  assertMetric(
    !initialResources.some((name) => name.includes('/data/enhanced-satellite-tiles/')),
    'Enhanced comparison tiles should not load by default on the raw imagery path'
  );
  assertMetric(
    !initialResources.some((name) => name.includes('titiler.xyz')),
    'Runtime TiTiler tiles should not load'
  );
  assertMetric(
    !initialResources.some((name) => name.includes('202611_nisar_losDisplacement/ImageServer/exportImage')),
    'NASA displacement overlay loaded before opt-in'
  );

  const comparisonStart = await page.evaluate(() => performance.now());
  const addressSearch = page.getByRole('textbox', { name: 'Search address or place in Venezuela' });
  await addressSearch.fill('Catia La Mar');
  await page.waitForFunction(() => document.querySelectorAll('.address-results [role="option"]').length > 0, null, { timeout: 15000 });
  await page.getByRole('option', { name: /Catia La Mar/ }).click();
  const slider = page.getByRole('slider', { name: 'Move before and after satellite comparison' });
  await slider.waitFor({ state: 'visible' });
  await waitForComparisonTiles(page, 'initial comparison');
  const comparisonReadyMs = await page.evaluate((start) => performance.now() - start, comparisonStart);
  await waitForComparisonTiles(page, 'initial comparison settled');
  const comparisonState = await page.evaluate((minTileNaturalWidth) => {
    const beforeImages = [...document.querySelectorAll('.comparison-before-tile-layer img')];
    const afterImages = [...document.querySelectorAll('.comparison-after-tile-layer img')];
    const damageImages = [...document.querySelectorAll('.damage-raster-layer img')];
    const allImages = [...beforeImages, ...afterImages];
    const validImages = allImages.filter((image) => image.complete && image.naturalWidth >= minTileNaturalWidth && image.naturalHeight >= minTileNaturalWidth);
    const urls = [
      ...performance.getEntriesByType('resource').map((entry) => entry.name),
      ...allImages.map((image) => image.currentSrc)
    ];
    const nationalImageryImages = [...document.querySelectorAll('.national-open-imagery-tile img')];
    const damageZooms = urls
      .filter((name) => name.includes('/data/damage-tiles/'))
      .map((name) => Number(name.match(/\/(\d+)\/\d+\/\d+\.png(?:\?.*)?$/)?.[1]))
      .filter(Boolean);
    const postEventVantorTiles = urls.filter((name) => name.includes('B15000110186C610.tif'));
    const preEventVantorTiles = urls.filter((name) => name.includes('B120001100513B10.tif'));
    const localEnhancedAfterTiles = urls.filter((name) => name.includes('/data/enhanced-satellite-tiles/after/'));
    const localEnhancedBeforeTiles = urls.filter((name) => name.includes('/data/enhanced-satellite-tiles/before/'));

    return {
      beforeImageCount: beforeImages.length,
      afterImageCount: afterImages.length,
      damageImageCount: damageImages.length,
      nationalImageryImageCount: nationalImageryImages.length,
      imageCount: allImages.length,
      completeCount: validImages.length,
      minNaturalWidth: Math.min(...allImages.map((image) => image.naturalWidth || 0)),
      minValidNaturalWidth: Math.min(...validImages.map((image) => image.naturalWidth || 0)),
      maxNaturalWidth: Math.max(...allImages.map((image) => image.naturalWidth || 0)),
      damageTileCount: damageZooms.length,
      minDamageZoom: Math.min(...damageZooms),
      maxDamageZoom: Math.max(...damageZooms),
      postEventVantorTileCount: postEventVantorTiles.length,
      preEventVantorTileCount: preEventVantorTiles.length,
      localEnhancedAfterTileCount: localEnhancedAfterTiles.length,
      localEnhancedBeforeTileCount: localEnhancedBeforeTiles.length,
      openAerialMapTileCount: urls.filter((name) => name.includes('tiles.openaerialmap.org')).length
    };
  }, thresholds.minTileNaturalWidth);

  assertMetric(comparisonReadyMs < thresholds.comparisonReadyMs, 'Before/after satellite comparison loaded too slowly', {
    comparisonReadyMs
  });
  assertMetric(
    comparisonState.beforeImageCount >= 8 &&
      comparisonState.afterImageCount >= 8 &&
      comparisonState.damageImageCount === 0 &&
      comparisonState.nationalImageryImageCount > 0,
    'Before/after satellite comparison tiles are incomplete or the open national imagery underlay is unavailable',
    comparisonState
  );
  assertMetric(
      comparisonState.minValidNaturalWidth >= thresholds.minTileNaturalWidth &&
      comparisonState.damageTileCount === 0 &&
      comparisonState.postEventVantorTileCount > 0 &&
      comparisonState.preEventVantorTileCount > 0 &&
      comparisonState.localEnhancedAfterTileCount === 0 &&
      comparisonState.localEnhancedBeforeTileCount === 0,
    'Comparison is not requesting canonical Vantor STAC 2x pre/post tiles or is loading damage/enhanced tiles before opt-in',
    comparisonState
  );
  assertMetric(
    comparisonState.openAerialMapTileCount === 0,
    'Clean comparison should use canonical Vantor STAC COG tiles, not OpenAerialMap fallback tiles',
    comparisonState
  );

  const box = await page.locator('.map-canvas').boundingBox();
  const clip = {
    x: Math.round(box.x),
    y: Math.round(box.y),
    width: Math.round(box.width),
    height: Math.round(box.height)
  };

  const afterMostly = await hiddenMapScreenshot(page, slider, clip, 8, 'comparison-after-mostly.png');
  const beforeMostly = await hiddenMapScreenshot(page, slider, clip, 92, 'comparison-before-mostly.png');
  const splitHalf = await hiddenMapScreenshot(page, slider, clip, 50, 'comparison-split-half.png');
  await page.screenshot({ path: `${outputDir}/comparison-visible-ui.png`, fullPage: false });

  const afterImage = parsePng(afterMostly);
  const beforeImage = parsePng(beforeMostly);
  const splitImage = parsePng(splitHalf);
  const centerCrop = {
    x0: afterImage.width * 0.18,
    y0: afterImage.height * 0.18,
    x1: afterImage.width * 0.82,
    y1: afterImage.height * 0.82
  };
  const beforeMetrics = imageMetrics(beforeImage, centerCrop);
  const afterMetrics = imageMetrics(afterImage, centerCrop);
  const splitMetrics = imageMetrics(splitImage, centerCrop);
  const fullDiff = diffMetrics(afterImage, beforeImage, centerCrop);
  const leftDiff = diffMetrics(afterImage, beforeImage, {
    x0: 0,
    y0: afterImage.height * 0.12,
    x1: afterImage.width * 0.45,
    y1: afterImage.height * 0.88
  });
  const rightDiff = diffMetrics(afterImage, beforeImage, {
    x0: afterImage.width * 0.55,
    y0: afterImage.height * 0.12,
    x1: afterImage.width,
    y1: afterImage.height * 0.88
  });

  assertImageQuality('before image', beforeMetrics);
  assertImageQuality('after image', afterMetrics);
  assertImageQuality('split image', splitMetrics);
  const qualityBalance = {
    stddevRatio: Math.max(beforeMetrics.stddev, afterMetrics.stddev) / Math.max(1, Math.min(beforeMetrics.stddev, afterMetrics.stddev)),
    gradientRatio: Math.max(beforeMetrics.gradient, afterMetrics.gradient) / Math.max(1, Math.min(beforeMetrics.gradient, afterMetrics.gradient)),
    laplacianRatio: Math.max(beforeMetrics.laplacian, afterMetrics.laplacian) / Math.max(1, Math.min(beforeMetrics.laplacian, afterMetrics.laplacian)),
    entropyDelta: Math.abs(beforeMetrics.entropy - afterMetrics.entropy),
    whiteRatioDelta: Math.abs(beforeMetrics.whiteRatio - afterMetrics.whiteRatio),
    darkRatioDelta: Math.abs(beforeMetrics.darkRatio - afterMetrics.darkRatio)
  };
  assertMetric(
    qualityBalance.stddevRatio < 1.8 &&
      qualityBalance.gradientRatio < 1.9 &&
      qualityBalance.laplacianRatio < 2.3 &&
      qualityBalance.entropyDelta < 1.0 &&
      qualityBalance.whiteRatioDelta < 0.18 &&
      qualityBalance.darkRatioDelta < 0.18,
    'Before/after satellite quality is imbalanced',
    { beforeMetrics, afterMetrics, qualityBalance }
  );
  assertMetric(
    fullDiff.meanAbsDiff > thresholds.minFullMeanAbsDiff && fullDiff.changedRatio > thresholds.minFullChangedRatio,
    'Before/after imagery difference is too weak',
    fullDiff
  );
  assertMetric(
    Math.max(leftDiff.changedRatio, rightDiff.changedRatio) > thresholds.minSideChangedRatio,
    'Slider extremes do not visibly affect the available map imagery',
    { leftDiff, rightDiff }
  );
  const splitLeftVsBefore = diffMetrics(splitImage, beforeImage, {
    x0: 0,
    y0: afterImage.height * 0.12,
    x1: afterImage.width * 0.45,
    y1: afterImage.height * 0.88
  });
  const splitLeftVsAfter = diffMetrics(splitImage, afterImage, {
    x0: 0,
    y0: afterImage.height * 0.12,
    x1: afterImage.width * 0.45,
    y1: afterImage.height * 0.88
  });
  const splitRightVsAfter = diffMetrics(splitImage, afterImage, {
    x0: afterImage.width * 0.55,
    y0: afterImage.height * 0.12,
    x1: afterImage.width,
    y1: afterImage.height * 0.88
  });
  const splitRightVsBefore = diffMetrics(splitImage, beforeImage, {
    x0: afterImage.width * 0.55,
    y0: afterImage.height * 0.12,
    x1: afterImage.width,
    y1: afterImage.height * 0.88
  });
  const rightSideHasNoDataDiff =
    splitRightVsAfter.changedRatio === 0 &&
    splitRightVsBefore.changedRatio === 0 &&
    rightDiff.changedRatio === 0;
  assertMetric(
    splitLeftVsBefore.meanAbsDiff + 2 < splitLeftVsAfter.meanAbsDiff &&
      (rightSideHasNoDataDiff || splitRightVsAfter.meanAbsDiff + 2 < splitRightVsBefore.meanAbsDiff),
    'Split comparison sides do not match expected before-left / after-right imagery',
    { splitLeftVsBefore, splitLeftVsAfter, splitRightVsAfter, splitRightVsBefore }
  );

  const damageButton = page.locator('.sidebar .layer-row').filter({ hasText: 'Damage' });
  await damageButton.scrollIntoViewIfNeeded();
  await damageButton.click();
  await page.waitForFunction(() => document.querySelector('.damage-legend')?.textContent?.includes('building footprints'), null, {
    timeout: 20000
  });
  await page.waitForFunction(
    () => {
      const damageImages = [...document.querySelectorAll('.comparison-damage-raster-layer img')];
      return damageImages.some((image) => image.complete && image.naturalWidth >= 256 && image.naturalHeight >= 256);
    },
    null,
    { timeout: 20000 }
  );
  await assertComparisonAlignment(page, 'imagery comparison with damage');
  const damageOptIn = await page.screenshot({ path: `${outputDir}/comparison-damage-opt-in.png`, clip });
  const damageOptInImage = parsePng(damageOptIn);
  const damageOptInColor = damageColorMetrics(damageOptInImage, centerCrop);
  const damageResources = await page.evaluate(() => {
    const urls = performance.getEntriesByType('resource').map((entry) => entry.name);
    const damageImages = [...document.querySelectorAll('.damage-raster-layer img')].map((image) => image.currentSrc);
    return {
      damageTileCount: [...urls, ...damageImages].filter((name) => name.includes('/data/damage-tiles/')).length
    };
  });
  assertMetric(
    damageResources.damageTileCount > 0,
    'Damage raster tiles did not load after damage opt-in',
    damageResources
  );
  assertMetric(
    damageOptInColor.damageColorRatio > thresholds.minDamageColorRatio,
    'Damage opt-in view does not show enough visible damage-colored pixels',
    damageOptInColor
  );

  await page.getByRole('button', { name: 'Hide' }).click();
  await page.waitForFunction(() => !document.querySelector('.comparison-control'), null, { timeout: 10000 });

  await clickButtonContaining(page, ['Key areas', 'Zonas clave'], 'Key affected areas');
  await page.locator('.worst-experience-panel').waitFor({ state: 'visible', timeout: 15000 });
  const worstAreaResults = [];
  worstAreaResults.push(await assertWorstAreaImagery(page, clip, 1));
  await clickButtonContaining(page, ['Next', 'Siguiente'], 'Next affected area');
  await page.waitForFunction(() => document.querySelector('.worst-experience-panel')?.textContent?.includes('2/3'), null, {
    timeout: 10000
  });
  worstAreaResults.push(await assertWorstAreaImagery(page, clip, 2));
  await clickButtonContaining(page, ['Next', 'Siguiente'], 'Next affected area');
  await page.waitForFunction(() => document.querySelector('.worst-experience-panel')?.textContent?.includes('3/3'), null, {
    timeout: 10000
  });
  worstAreaResults.push(await assertWorstAreaImagery(page, clip, 3));

  assertMetric(!consoleIssues.length, 'Console issues detected', { consoleIssues });

  const navigation = await page.evaluate(() => {
    const entry = performance.getEntriesByType('navigation')[0];
    return entry
      ? {
          domContentLoaded: Math.round(entry.domContentLoadedEventEnd),
          loadEventEnd: Math.round(entry.loadEventEnd),
          duration: Math.round(entry.duration)
        }
      : null;
  });
  const summary = {
    appUrl,
    comparisonReadyMs: Math.round(comparisonReadyMs),
    navigation,
    comparisonState,
    beforeMetrics,
    afterMetrics,
    splitMetrics,
    fullDiff,
    damageResources,
    damageOptInColor,
    worstAreaResults,
    leftDiff,
    rightDiff,
    screenshots: {
      afterMostly: `${outputDir}/comparison-after-mostly.png`,
      beforeMostly: `${outputDir}/comparison-before-mostly.png`,
      splitHalf: `${outputDir}/comparison-split-half.png`,
      damageOptIn: `${outputDir}/comparison-damage-opt-in.png`,
      visibleUi: `${outputDir}/comparison-visible-ui.png`,
      worstAreas: worstAreaResults.map((result) => result.screenshot)
    },
    consoleIssues
  };

  await writeFile(`${outputDir}/summary.json`, `${JSON.stringify(summary, null, 2)}\n`);
  console.log(JSON.stringify(summary, null, 2));
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
