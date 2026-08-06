import express from 'express';
import cors from 'cors';
import compression from 'compression';
import { HfInference } from '@huggingface/inference';
import { z } from 'zod';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import 'dotenv/config';

const app = express();
const port = Number(process.env.PORT || process.env.API_PORT || 8787);
const hfToken = process.env.HF_TOKEN || process.env.HUGGINGFACE_TOKEN || '';
const hfModel = process.env.HF_TRIAGE_MODEL || 'mistralai/Mistral-7B-Instruct-v0.3';
const hf = hfToken ? new HfInference(hfToken) : null;
const allowedCorsOrigins = (process.env.APP_ORIGINS || process.env.PUBLIC_APP_ORIGINS || '')
  .split(',')
  .map((origin) => origin.trim())
  .filter(Boolean);
const defaultCorsOrigins = [
  'https://sergiopesch-ayudavenezuela2026.hf.space',
  process.env.SPACE_HOST ? `https://${process.env.SPACE_HOST}` : '',
  process.env.HF_SPACE_HOST ? `https://${process.env.HF_SPACE_HOST}` : ''
].filter(Boolean);
const triageRateLimitWindowMs = Number(process.env.TRIAGE_RATE_LIMIT_WINDOW_MS || 60_000);
const triageRateLimitMax = Number(process.env.TRIAGE_RATE_LIMIT_MAX || 20);
const hfTimeoutMs = Number(process.env.HF_TRIAGE_TIMEOUT_MS || 20_000);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(__dirname, '..', 'dist');
const trustedDataPaths = [
  path.resolve(__dirname, '..', 'public/data/trusted-data.json'),
  path.resolve(distDir, 'data/trusted-data.json')
];
const triageCategories = [
  'SAR',
  'MED',
  'MISSING',
  'SHELTER',
  'WASH',
  'FOOD',
  'POWER_COMMS',
  'CONNECTIVITY',
  'LOGISTICS',
  'PROTECTION',
  'CASH',
  'INFRA',
  'RUMOR',
  'OFFER',
  'OTHER'
];
const triageUrgencies = ['U0', 'U1', 'U2', 'U3', 'U4'];
const transparentPng = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAAGYktHRAD/AP8A/6C9p5MAAAAldEVYdGRhdGU6Y3JlYXRlADIwMjYtMDYtMjdUMjA6MTU6MTkrMDA6MDBVj8q3AAAAJXRFWHRkYXRlOm1vZGlmeQAyMDI2LTA2LTI3VDIwOjE1OjE5KzAwOjAwJNJyCwAAACh0RVh0ZGF0ZTp0aW1lc3RhbXAAMjAyNi0wNi0yN1QyMDoxNToxOSswMDowMHPHU9QAAAALSURBVAjXY2AAAgAABQAB4iYFmwAAAABJRU5ErkJggg==',
  'base64'
);

app.set('trust proxy', 1);
app.use((req, res, next) => {
  res.setHeader('Content-Security-Policy', [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://server.arcgisonline.com https://tiles.maps.eox.at https://tiles.openaerialmap.org https://titiler.hotosm.org https://gis.earthdata.nasa.gov",
    "connect-src 'self' https://nominatim.openstreetmap.org https://gis.earthdata.nasa.gov",
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'"
  ].join('; '));
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  next();
});
app.use(cors({
  origin(origin, callback) {
    if (!origin) {
      callback(null, true);
      return;
    }

    if (
      defaultCorsOrigins.includes(origin) ||
      allowedCorsOrigins.includes(origin) ||
      /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(origin)
    ) {
      callback(null, true);
      return;
    }

    callback(new Error('CORS origin not allowed'));
  }
}));
app.use((error, _req, res, next) => {
  if (error instanceof Error && error.message === 'CORS origin not allowed') {
    res.status(403).json({ error: 'CORS origin not allowed' });
    return;
  }

  next(error);
});
app.use(compression({ threshold: 0 }));
app.use(express.json({ limit: '1mb' }));

function setStaticCacheHeaders(res, filePath) {
  const normalized = filePath.split(path.sep).join('/');
  if (normalized.includes('/assets/') || normalized.includes('/data/sentinel-tiles/') || normalized.includes('/data/damage-tiles/')) {
    res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
    return;
  }

  if (normalized.includes('/data/')) {
    res.setHeader('Cache-Control', 'public, max-age=300, stale-while-revalidate=86400');
    return;
  }

  res.setHeader('Cache-Control', 'public, max-age=0, must-revalidate');
}

const reportSchema = z.object({
  id: z.string().min(1).max(128),
  title: z.string().min(1).max(180),
  description: z.string().min(1).max(4000),
  category: z.enum(triageCategories),
  urgency: z.enum(triageUrgencies),
  locationText: z.string().min(1).max(500),
  source: z.string().min(1).max(64),
  sourceLabel: z.string().min(1).max(120),
  verification: z.string().min(1).max(64),
  confidence: z.number().optional(),
  safetyFlags: z.array(z.string().max(80)).max(16).optional(),
  publicSafe: z.boolean().optional(),
  consent: z.object({
    canContact: z.boolean(),
    canShareWithPartners: z.boolean(),
    canPublishPublicly: z.boolean()
  })
});

const triageRateLimit = new Map();
let lastRateLimitPruneAt = 0;
const sensitiveSafetyFlags = new Set([
  'contains_child_data',
  'contains_health_data',
  'contains_gbv_or_protection_data',
  'contains_migration_status',
  'contains_exact_private_location',
  'contains_photo_of_person',
  'potential_security_risk',
  'unsafe_to_publish'
]);

const requestSchema = z.object({
  report: reportSchema
});

const responseSchema = z.object({
  reportId: z.string(),
  summary: z.string(),
  category: z.enum(triageCategories),
  urgency: z.enum(triageUrgencies),
  confidence: z.number().min(0).max(1),
  action: z.string(),
  rationale: z.string(),
  hfStatus: z.enum(['hf_processed', 'local_fallback', 'pending', 'error'])
});

function localTriage(report) {
  const text = `${report.title} ${report.description}`.toLowerCase();
  let category = report.category;
  let urgency = report.urgency;
  const reasons = [];

  if (/(atrapad|rubble|escombro|grito|colaps|derrum|trapped)/.test(text)) {
    category = 'SAR';
    urgency = 'U0';
    reasons.push('possible trapped people or structural collapse');
  }
  if (/(herid|clinica|hospital|sangre|fractura|ambulancia|medic|trauma)/.test(text)) {
    category = category === 'SAR' ? category : 'MED';
    urgency = urgency === 'U0' ? urgency : 'U1';
    reasons.push('medical terms detected');
  }
  if (/(desaparecid|missing|ultimo contacto|no aparece|busca)/.test(text)) {
    category = 'MISSING';
    urgency = urgency === 'U0' ? urgency : 'U1';
    reasons.push('missing-person language detected');
  }
  if (/(starlink|hotspot|internet|senal|conect|wifi|carga|bateria|telefono)/.test(text)) {
    category = 'CONNECTIVITY';
    urgency = urgency === 'U0' || urgency === 'U1' ? urgency : 'U2';
    reasons.push('connectivity or charging terms detected');
  }
  if (/(agua|alimento|comida|higiene|panal|leche|water|food)/.test(text)) {
    category = category === 'CONNECTIVITY' ? category : report.category === 'FOOD' ? 'FOOD' : 'WASH';
    urgency = urgency === 'U0' ? urgency : 'U1';
    reasons.push('WASH/food terms detected');
  }

  return responseSchema.parse({
    reportId: report.id,
    summary: `${report.title} - ${report.locationText}`,
    category,
    urgency,
    confidence: Math.min(0.94, Math.max(report.confidence || 0.58, reasons.length ? 0.72 + reasons.length * 0.05 : 0.58)),
    action:
      category === 'CONNECTIVITY'
        ? 'Verify exact location and publish only if safe.'
        : category === 'MISSING'
          ? 'Route privately to family tracing validators.'
          : category === 'SAR'
            ? 'Escalate to SAR coordinator after contact/photo verification.'
            : 'Route to relevant cluster or local partner.',
    rationale: reasons.length ? reasons.join('; ') : 'Used existing category and verification metadata.',
    hfStatus: 'local_fallback'
  });
}

function extractJson(content) {
  const trimmed = content.trim();
  if (trimmed.startsWith('{')) return JSON.parse(trimmed);
  const match = trimmed.match(/\{[\s\S]*\}/);
  if (!match) throw new Error('No JSON object found in Hugging Face response');
  return JSON.parse(match[0]);
}

function rateLimitTriage(req, res, next) {
  const key = req.ip || req.socket.remoteAddress || 'unknown';
  const now = Date.now();

  if (now - lastRateLimitPruneAt >= triageRateLimitWindowMs) {
    for (const [bucketKey, bucket] of triageRateLimit.entries()) {
      if (now - bucket.startedAt >= triageRateLimitWindowMs) triageRateLimit.delete(bucketKey);
    }
    lastRateLimitPruneAt = now;
  }

  const bucket = triageRateLimit.get(key);
  if (!bucket || now - bucket.startedAt >= triageRateLimitWindowMs) {
    triageRateLimit.set(key, { startedAt: now, count: 1 });
    next();
    return;
  }

  bucket.count += 1;
  if (bucket.count > triageRateLimitMax) {
    res.setHeader('Retry-After', String(Math.ceil((triageRateLimitWindowMs - (now - bucket.startedAt)) / 1000)));
    res.status(429).json({ error: 'triage rate limit exceeded' });
    return;
  }

  next();
}

function shouldUseLocalOnlyTriage(report) {
  const safetyFlags = report.safetyFlags || [];
  return (
    !report.consent.canShareWithPartners ||
    !report.consent.canPublishPublicly ||
    report.publicSafe === false ||
    safetyFlags.some((flag) => sensitiveSafetyFlags.has(flag)) ||
    containsSensitiveReportContent(report)
  );
}

function containsSensitiveReportContent(report) {
  const text = [
    report.title,
    report.description,
    report.locationText,
    report.sourceLabel,
    report.verification
  ].join('\n').toLowerCase();

  return [
    /\b(?:\+?58|0)(?:\s|-|\.)?(?:2\d{2}|4(?:12|14|16|24|26))(?:\s|-|\.)?\d{3}(?:\s|-|\.)?\d{4}\b/,
    /\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b/,
    /\b(?:cedula|c[eé]dula|passport|pasaporte|id number|documento)\b/,
    /\b(?:menor|niñ[oa]|child|children|embarazad[ao]|pregnant|ancian[oa]|elderly)\b/,
    /\b(?:herid[ao]|sangre|fractura|trauma|hospital|clinica|cl[ií]nica|diagn[oó]stico|medical|medic[ao])\b/,
    /\b(?:violencia sexual|gbv|abuso|protecci[oó]n|migration status|estatus migratorio)\b/,
    /\b(?:casa|apartamento|apto|piso|edificio|torre|urbanizaci[oó]n|calle|avenida|av\.|sector|barrio)\b.*\b(?:\d{1,5}|casa|apto|apartamento|piso)\b/
  ].some((pattern) => pattern.test(text));
}

function sanitizeReportForModel(report) {
  return {
    id: report.id,
    title: report.title,
    description: report.description,
    category: report.category,
    urgency: report.urgency,
    locationText: report.locationText,
    source: report.source,
    verification: report.verification,
    confidence: report.confidence,
    safetyFlags: report.safetyFlags || [],
    consent: {
      canShareWithPartners: report.consent.canShareWithPartners,
      canPublishPublicly: report.consent.canPublishPublicly
    }
  };
}

async function withTimeout(promise, timeoutMs) {
  let timeout;
  const timeoutPromise = new Promise((_, reject) => {
    timeout = setTimeout(() => reject(new Error(`HF request timed out after ${timeoutMs}ms`)), timeoutMs);
  });

  try {
    return await Promise.race([promise, timeoutPromise]);
  } finally {
    clearTimeout(timeout);
  }
}

app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    hfConfigured: Boolean(hf),
    model: hfModel
  });
});

app.get('/api/trusted-data', async (_req, res) => {
  for (const trustedDataPath of trustedDataPaths) {
    try {
      const payload = await readFile(trustedDataPath, 'utf8');
      res.setHeader('Cache-Control', 'public, max-age=300, stale-while-revalidate=86400');
      res.type('application/json').send(payload);
      return;
    } catch {
      // Try the next location; dev uses public/, production uses dist/.
    }
  }

  res.status(503).json({ error: 'trusted data snapshot unavailable' });
});

app.post('/api/hf/triage', rateLimitTriage, async (req, res) => {
  const parsed = requestSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.flatten() });
    return;
  }

  const { report } = parsed.data;
  const localOnly = shouldUseLocalOnlyTriage(report);

  if (!hf || localOnly) {
    const triage = localTriage(report);
    res.json({
      ...triage,
      rationale: localOnly
        ? `${triage.rationale} Local-only triage used because consent, publication safety, or server-side sensitive-content checks block third-party model processing.`
        : triage.rationale
    });
    return;
  }

  try {
    const modelReport = sanitizeReportForModel(report);
    const completion = await withTimeout(hf.chatCompletion({
      model: hfModel,
      messages: [
        {
          role: 'system',
          content:
            'You are a humanitarian disaster report triage assistant for Venezuela earthquake response. Return only strict JSON. Do not invent facts. Never recommend public publication of sensitive personal data.'
        },
        {
          role: 'user',
          content: `Classify and triage this minimized report. Categories: SAR, MED, MISSING, SHELTER, WASH, FOOD, POWER_COMMS, CONNECTIVITY, LOGISTICS, PROTECTION, CASH, INFRA, RUMOR, OFFER, OTHER. Urgency: U0 immediate life safety, U1 same day, U2 1-3 days, U3 monitor, U4 closed. Return JSON with reportId, summary, category, urgency, confidence 0-1, action, rationale, hfStatus="hf_processed".\n\nReport:\n${JSON.stringify(modelReport, null, 2)}`
        }
      ],
      max_tokens: 450,
      temperature: 0.1
    }), hfTimeoutMs);

    const content = completion.choices?.[0]?.message?.content || '';
    const aiJson = extractJson(content);
    const validated = responseSchema.parse({
      ...aiJson,
      reportId: report.id,
      hfStatus: 'hf_processed'
    });

    res.json(validated);
  } catch (error) {
    console.error('[hf-triage]', error);
    res.json({
      ...localTriage(report),
      hfStatus: 'error',
      rationale: `HF request failed; local fallback used. ${error instanceof Error ? error.message : 'Unknown error'}`
    });
  }
});

app.use(express.static(distDir, { setHeaders: setStaticCacheHeaders }));

app.get(/^\/data\/damage-tiles\/\d+\/\d+\/\d+\.png$/, (_req, res) => {
  res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
  res.type('png').send(transparentPng);
});

app.use((req, res, next) => {
  if (req.method !== 'GET' || req.path.startsWith('/api/')) {
    next();
    return;
  }

  res.sendFile(path.join(distDir, 'index.html'));
});

app.use((error, req, res, _next) => {
  const status =
    error instanceof SyntaxError && 'body' in error
      ? 400
      : error instanceof Error && error.message === 'CORS origin not allowed'
        ? 403
        : 500;

  if (res.headersSent) return;

  if (req.path.startsWith('/api/')) {
    res.status(status).json({
      error: status === 500 ? 'internal server error' : error.message
    });
    return;
  }

  res.status(status).type('text/plain').send(status === 500 ? 'Internal server error' : error.message);
});

const server = app.listen(port, () => {
  console.log(`AyudaVenezuela2026 listening on http://localhost:${port}`);
  console.log(hf ? `HF triage enabled with ${hfModel}` : 'HF triage fallback mode: set HF_TOKEN to enable Hugging Face calls');
});

server.keepAliveTimeout = 65_000;
const lifecycleInterval = setInterval(() => {}, 2 ** 31 - 1);

function shutdown() {
  clearInterval(lifecycleInterval);
  server.close(() => {
    process.exitCode = 0;
  });
}

process.once('SIGINT', shutdown);
process.once('SIGTERM', shutdown);
