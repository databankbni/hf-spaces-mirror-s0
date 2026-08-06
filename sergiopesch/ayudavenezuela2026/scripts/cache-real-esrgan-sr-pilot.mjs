import { execFile } from 'node:child_process';
import { copyFile, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { promisify } from 'node:util';
import path from 'node:path';

const execFileAsync = promisify(execFile);

const repoId = process.env.SR_OUTPUT_REPO || 'sergiopesch/ayudavenezuela2026-enhanced-satellite-tiles';
const remotePrefix = 'super-resolution/real-esrgan-pilot';
const reportFile = process.env.SR_REPORT_FILE || `${remotePrefix}/report-20260702.json`;
const contactSheetFile = process.env.SR_CONTACT_SHEET_FILE || `${remotePrefix}/contact-sheet-20260702.jpg`;
const publicRoot = path.resolve('public/data/super-resolution/real-esrgan-pilot');
const tmpRoot = path.resolve('/tmp/ayuda-real-esrgan-sr-pilot');

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
    maxBuffer: 1024 * 1024 * 12
  });
  return path.join(tmpRoot, filename);
}

function publicAssetPath(filename) {
  return `/data/super-resolution/real-esrgan-pilot/${filename}`;
}

function hubUrl(filename) {
  return `https://huggingface.co/datasets/${repoId}/resolve/main/${filename}`;
}

async function main() {
  await rm(tmpRoot, { recursive: true, force: true });
  await mkdir(publicRoot, { recursive: true });

  const reportPath = await hfDownload(reportFile);
  const contactSheetPath = await hfDownload(contactSheetFile);
  const report = JSON.parse(await readFile(reportPath, 'utf8'));
  const archiveName = process.env.SR_ARCHIVE_NAME ||
    `ayudavenezuela2026-real-esrgan-affected-areas-z19-aoi${report.completedAois || report.requestedAois || 'unknown'}-20260702.tar`;
  const archiveFile = `${remotePrefix}/${archiveName}`;

  await copyFile(contactSheetPath, path.join(publicRoot, 'contact-sheet.jpg'));
  await copyFile(reportPath, path.join(publicRoot, 'report.json'));

  const index = {
    generatedAt: report.generatedAt,
    type: report.type,
    model: report.model,
    zoom: report.zoom,
    requestedAois: report.requestedAois,
    completedAois: report.completedAois,
    records: (report.records || []).map((record) => ({
      id: record.id,
      lon: record.lon,
      lat: record.lat,
      severity: record.severity,
      tile: record.tile,
      model: record.model,
      interpretive: record.interpretive,
      warning: record.warning
    })),
    source: report.source,
    useGuidance: report.useGuidance,
    contactSheet: {
      localPath: publicAssetPath('contact-sheet.jpg'),
      hfPath: contactSheetFile,
      url: hubUrl(contactSheetFile)
    },
    report: {
      localPath: publicAssetPath('report.json'),
      hfPath: reportFile,
      url: hubUrl(reportFile)
    },
    archive: {
      name: archiveName,
      hfPath: archiveFile,
      url: hubUrl(archiveFile)
    }
  };

  await writeFile(path.join(publicRoot, 'index.json'), `${JSON.stringify(index, null, 2)}\n`, 'utf8');
  console.log(`Real-ESRGAN SR pilot: ${index.completedAois} AOIs -> ${publicRoot}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
