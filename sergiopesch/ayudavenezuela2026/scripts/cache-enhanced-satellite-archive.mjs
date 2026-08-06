import { execFile } from 'node:child_process';
import { mkdir, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const repoId = process.env.ENHANCED_TILE_OUTPUT_REPO || 'sergiopesch/ayudavenezuela2026-enhanced-satellite-tiles';
const archiveName = process.env.ENHANCED_TILE_ARCHIVE_NAME ||
  'ayudavenezuela2026-enhanced-satellite-tiles-z18-z19-20260702.tar';
const tmpRoot = resolve(process.env.ENHANCED_TILE_ARCHIVE_TMP || '/tmp/ayuda-enhanced-satellite-archive');
const publicDataRoot = resolve('public/data');
const outputRoot = resolve('public/data/enhanced-satellite-tiles');

async function hfDownload(filename) {
  await execFileAsync('hf', [
    'download',
    repoId,
    filename,
    '--repo-type',
    'dataset',
    '--local-dir',
    tmpRoot,
    '--force-download'
  ], {
    maxBuffer: 1024 * 1024 * 16
  });
  return resolve(tmpRoot, filename);
}

await mkdir(tmpRoot, { recursive: true });
await rm(outputRoot, { recursive: true, force: true });

const archivePath = await hfDownload(archiveName);
await hfDownload('manifest.json');
await execFileAsync('tar', ['-xf', archivePath, '-C', publicDataRoot], {
  maxBuffer: 1024 * 1024 * 16
});

console.log(`Enhanced satellite archive unpacked to ${outputRoot}`);
