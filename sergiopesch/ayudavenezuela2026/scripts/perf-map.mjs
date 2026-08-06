import { chromium } from 'playwright';
import { existsSync, readdirSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';

const appUrl = process.env.PERF_URL || 'http://127.0.0.1:8787/';
const outputDir = process.env.PERF_OUTPUT_DIR || '/tmp/ayuda-map-perf';
const iterations = Number(process.env.PERF_RUNS || 1);
const mockExternalTiles = process.env.PERF_MOCK_EXTERNAL_TILES !== '0';
const mockTileSvg = Buffer.from(
  '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#d7e3d8"/><path d="M0 190 70 150 130 170 210 120 256 142v114H0z" fill="#7f9f72"/><path d="M0 82h256" stroke="#a8b8bd" stroke-width="18" opacity=".55"/></svg>'
);
const budgets = {
  firstTileMs: Number(process.env.PERF_FIRST_TILE_MS || 1800),
  comparisonReadyMs: Number(process.env.PERF_COMPARISON_READY_MS || 45000),
  damageReadyMs: Number(process.env.PERF_DAMAGE_READY_MS || 55000),
  networkIdleMs: Number(process.env.PERF_NETWORK_IDLE_MS || 65000),
  transferBytes: Number(process.env.PERF_TRANSFER_BYTES || 8000000)
};

const viewports = [
  ['desktop', { width: 1440, height: 980, isMobile: false }],
  ['mobile', { width: 390, height: 900, isMobile: true }]
];

function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p))];
}

function summarize(samples) {
  const keys = ['firstTileMs', 'comparisonReadyMs', 'damageReadyMs', 'networkIdleMs', 'transferBytes'];
  return Object.fromEntries(keys.map((key) => [key, {
    min: Math.min(...samples.map((sample) => sample[key])),
    median: percentile(samples.map((sample) => sample[key]), 0.5),
    max: Math.max(...samples.map((sample) => sample[key]))
  }]));
}

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

async function enableComparison(page) {
  const addressSearch = page.getByRole('textbox', { name: 'Search address or place in Venezuela' });
  await addressSearch.fill('Catia La Mar');
  await page.waitForFunction(() => document.querySelectorAll('.address-results [role="option"]').length > 0, null, { timeout: 15000 });
  await page.getByRole('option', { name: /Catia La Mar/ }).click();
  await page.getByRole('slider', { name: 'Move before and after satellite comparison' }).waitFor({ state: 'visible' });
}

async function enableDamage(page, viewport) {
  if (viewport.isMobile) {
    const mapLayers = page.getByRole('button', { name: 'Map layers' });
    if (!(await page.locator('.mobile-map-controls').isVisible())) await mapLayers.click();
    await page.locator('.mobile-map-controls .layer-row').filter({ hasText: 'Damage' }).click();
    return;
  }
  await page.locator('.sidebar .layer-row').filter({ hasText: 'Damage' }).click();
}

await mkdir(outputDir, { recursive: true });
const chromiumExecutablePath =
  process.env.CHROMIUM_EXECUTABLE_PATH ||
  cachedPlaywrightChromiumExecutable() ||
  [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
  ].find((path) => existsSync(path));
const browser = await chromium.launch({
  headless: true,
  ...(chromiumExecutablePath ? { executablePath: chromiumExecutablePath } : {})
});
const failures = [];
const results = [];

for (const [viewportName, viewport] of viewports) {
  const samples = [];

  for (let run = 1; run <= iterations; run += 1) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      isMobile: viewport.isMobile,
      deviceScaleFactor: 1,
      bypassCSP: true
    });
    const page = await context.newPage();
    const consoleIssues = [];
    const failedRequests = [];

    page.on('console', (message) => {
      if (['error', 'warning'].includes(message.type())) consoleIssues.push(`${message.type()}: ${message.text()}`);
    });
    page.on('requestfailed', (request) => {
      const errorText = request.failure()?.errorText || 'failed';
      const url = request.url();
      if (errorText === 'net::ERR_ABORTED' && url.includes('s2cloudless-2024_3857')) return;
      if (errorText === 'net::ERR_ABORTED' && url.includes('tiles.openaerialmap.org')) return;
      if (errorText === 'net::ERR_ABORTED' && url.includes('titiler.hotosm.org/cog/tiles/')) return;
      failedRequests.push(`${errorText} ${url}`);
    });
    if (mockExternalTiles) {
      await page.route(/https:\/\/(?:tiles\.maps\.eox\.at|tiles\.openaerialmap\.org|titiler\.hotosm\.org)\/.*/, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'image/svg+xml',
          body: mockTileSvg
        });
      });
    }
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
            lat: '10.602000',
            lon: '-67.030000',
            type: 'town',
            class: 'place',
            importance: 0.78,
            boundingbox: ['10.601900', '10.602100', '-67.030100', '-67.029900'],
            address: {
              town: 'Catia La Mar',
              state: 'La Guaira',
              country: 'Venezuela'
            }
          }
        ])
      });
    });

    const start = Date.now();
    await page.goto(appUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.getByRole('button', { name: /English/ }).click();
    await page.waitForFunction(() => {
      return [...document.querySelectorAll('.leaflet-tile')].some((image) =>
        image.complete && image.naturalWidth >= 256
      );
    }, null, { timeout: 30000 });
    const firstTileMs = Date.now() - start;
    await enableComparison(page, viewport);
    await page.waitForFunction(
      () => {
        const loaded = (image) => image.complete && image.naturalWidth >= 256 && image.naturalHeight >= 256;
        const beforeImages = [...document.querySelectorAll('.comparison-before-tile-layer img')];
        const afterImages = [...document.querySelectorAll('.comparison-after-tile-layer img')];
        return beforeImages.some(loaded) && afterImages.some(loaded);
      },
      null,
      { timeout: 60000 }
    );
    const comparisonReadyMs = Date.now() - start;
    await enableDamage(page, viewport);
    await page.waitForFunction(
      () => {
        const loaded = (image) => image.complete && image.naturalWidth >= 256 && image.naturalHeight >= 256;
        return [...document.querySelectorAll('.comparison-damage-raster-layer img')].some(loaded) &&
          /\d[\d,]*\s+(building footprints|huellas de edificios)/.test(document.querySelector('.damage-legend')?.textContent || '');
      },
      null,
      { timeout: 30000 }
    );
    const damageReadyMs = Date.now() - start;
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => undefined);
    const networkIdleMs = Date.now() - start;

    if (run === 1) {
      await page.screenshot({ path: `${outputDir}/${viewportName}.png`, fullPage: true });
    }

    const resourceSummary = await page.evaluate(() => {
      const entries = performance.getEntriesByType('resource');
      const tiles = [...document.querySelectorAll('.leaflet-tile')];
      const damageImages = [...document.querySelectorAll('.damage-raster-layer img')].map((image) => image.currentSrc);
      const resourceUrls = [...entries.map((entry) => entry.name), ...damageImages];
      const mapRect = document.querySelector('.map-canvas')?.getBoundingClientRect();
      const isVisibleTile = (image) => {
        if (!mapRect) return true;
        const rect = image.getBoundingClientRect();
        return rect.right > mapRect.left && rect.left < mapRect.right && rect.bottom > mapRect.top && rect.top < mapRect.bottom;
      };
      return {
        loadedTiles: document.querySelectorAll('.leaflet-tile-loaded').length,
        erroredTiles: tiles.filter((image) =>
          image.complete &&
          image.naturalWidth === 0 &&
          Boolean(image.currentSrc) &&
          !image.currentSrc.startsWith('data:') &&
          isVisibleTile(image) &&
          !image.currentSrc.includes('s2cloudless-2024_3857')
        ).length,
        jpegTiles: entries.filter((entry) => entry.name.includes('/data/sentinel-tiles/') && entry.name.endsWith('.jpg')).length,
        pngTiles: entries.filter((entry) => entry.name.includes('/data/sentinel-tiles/') && entry.name.endsWith('.png')).length,
        damageTiles: resourceUrls.filter((name) => name.includes('/data/damage-tiles/') && name.endsWith('.png')).length,
        damageViewIndex: entries.filter((entry) => entry.name.includes('/data/damage-view-index.json')).length,
        damageGzip: entries.filter((entry) => entry.name.includes('/data/microsoft-damage-catia-lite.geojson.gz')).length,
        damagePlain: entries.filter((entry) => entry.name.includes('/data/microsoft-damage-catia-lite.geojson')).length,
        damageFull: entries.filter((entry) => entry.name.includes('/data/microsoft-damage-catia.geojson')).length,
        titilerRequests: entries.filter((entry) => entry.name.includes('titiler.xyz')).length,
        arcgisDamageRequests: entries.filter((entry) => entry.name.includes('Catia_La_Mar_3D_WFL1/FeatureServer')).length,
        nationalOpenImageryTiles: entries.filter((entry) => entry.name.includes('s2cloudless-2024_3857')).length,
        transferBytes: entries.reduce((sum, entry) => sum + (entry.transferSize || 0), 0)
      };
    });

    const sample = {
      viewport: viewportName,
      run,
      firstTileMs,
      comparisonReadyMs,
      damageReadyMs,
      networkIdleMs,
      transferBytes: resourceSummary.transferBytes,
      resourceSummary,
      consoleIssues,
      failedRequests
    };
    samples.push(sample);

    if (consoleIssues.length) failures.push(`${viewportName} run ${run}: console issues: ${consoleIssues.join('; ')}`);
    if (failedRequests.length) failures.push(`${viewportName} run ${run}: request failures: ${failedRequests.join('; ')}`);
    if (resourceSummary.erroredTiles && failedRequests.length) failures.push(`${viewportName} run ${run}: ${resourceSummary.erroredTiles} tile image errors`);
    if (!resourceSummary.nationalOpenImageryTiles) failures.push(`${viewportName} run ${run}: EOX Sentinel-2 Cloudless imagery tiles were not used`);
    if (!resourceSummary.damageTiles) failures.push(`${viewportName} run ${run}: damage raster tiles were not used after opt-in`);
    if (resourceSummary.damageViewIndex !== 1) failures.push(`${viewportName} run ${run}: compact damage view index was not used exactly once`);
    if (resourceSummary.damageGzip || resourceSummary.damagePlain) failures.push(`${viewportName} run ${run}: initial map requested damage GeoJSON instead of raster tiles`);
    if (resourceSummary.damageFull) failures.push(`${viewportName} run ${run}: old full damage GeoJSON was requested`);
    if (resourceSummary.pngTiles) failures.push(`${viewportName} run ${run}: stale PNG Sentinel tiles were requested`);
    if (resourceSummary.titilerRequests) failures.push(`${viewportName} run ${run}: runtime TiTiler requests were made`);
    if (resourceSummary.arcgisDamageRequests) failures.push(`${viewportName} run ${run}: live ArcGIS damage requests were made`);

    await context.close();
  }

  const stats = summarize(samples);
  results.push({ viewport: viewportName, stats, samples });

  if (stats.firstTileMs.max > budgets.firstTileMs) failures.push(`${viewportName}: max first tile ${stats.firstTileMs.max}ms exceeds ${budgets.firstTileMs}ms`);
  if (stats.comparisonReadyMs.max > budgets.comparisonReadyMs) failures.push(`${viewportName}: max comparison ready ${stats.comparisonReadyMs.max}ms exceeds ${budgets.comparisonReadyMs}ms`);
  if (stats.damageReadyMs.max > budgets.damageReadyMs) failures.push(`${viewportName}: max damage ready ${stats.damageReadyMs.max}ms exceeds ${budgets.damageReadyMs}ms`);
  if (stats.networkIdleMs.max > budgets.networkIdleMs) failures.push(`${viewportName}: max network idle ${stats.networkIdleMs.max}ms exceeds ${budgets.networkIdleMs}ms`);
  if (stats.transferBytes.max > budgets.transferBytes) failures.push(`${viewportName}: max transfer ${stats.transferBytes.max} bytes exceeds ${budgets.transferBytes}`);
}

await browser.close();

const report = { appUrl, iterations, budgets, results, failures };
console.log(JSON.stringify(report, null, 2));

if (failures.length) process.exitCode = 1;
