import { readFileSync } from 'fs';
import { join } from 'path';
import Fastify, { FastifyInstance } from 'fastify';
import cors from '@fastify/cors';
import { config } from './config';
import { chatRoutes } from './api/chat.controller';
import demoMenu from './demo/demo-menu.json';

/**
 * Server bootstrap
 * ----------------
 * Fastify is chosen over Express for its low overhead and built-in schema/
 * logging support — a good fit for a stateless, latency-sensitive AI service.
 *
 * The service is intentionally tiny and stateless: no database, no sessions.
 * Scale it by running more instances behind a load balancer.
 */

export function buildServer(): FastifyInstance {
  const app = Fastify({
    logger: {
      level: config.logLevel,
      transport:
        process.env.NODE_ENV === 'production'
          ? undefined
          : { target: 'pino-pretty', options: { translateTime: 'HH:MM:ss', ignore: 'pid,hostname' } },
    },
    // Reject oversized payloads early.
    bodyLimit: 64 * 1024,
  });

  // CORS so the existing frontend can call this service from the browser.
  app.register(cors, {
    origin: config.corsOrigin === '*' ? true : config.corsOrigin.split(',').map((s) => s.trim()),
    methods: ['GET', 'POST'],
  });

  // Demo mode: serve the built-in sample menu on the same path shape as the
  // real Django backend, so the whole pipeline works with zero external
  // dependencies (used on Hugging Face until the real backend is connected).
  if (config.demoMode) {
    app.get('/api/restaurants/:slug/menu/', async () => demoMenu);
    app.log.info('DEMO MODE: serving built-in sample menu (no real backend configured)');
  }

  // Simple built-in test chat UI at GET /ui (handy for demos & QA).
  // Served from the project's /public folder; harmless if the file is absent.
  app.get('/ui', async (_req, reply) => {
    try {
      const html = readFileSync(join(__dirname, '..', 'public', 'index.html'), 'utf8');
      return reply.type('text/html').send(html);
    } catch {
      return reply.code(404).send({ error: 'Test UI not found (public/index.html missing).' });
    }
  });

  // Learned guest insights per restaurant — for owner dashboards and for the
  // backend to harvest/store permanently (what MLO has learned from chats).
  app.get('/api/ai/insights', async (req, reply) => {
    const slug = (req.query as { slug?: string }).slug?.trim();
    if (!slug) {
      return reply.code(400).send({ error: 'Query parameter "slug" is required.' });
    }
    const { learningService } = await import('./services/learning.service');
    return learningService.snapshot(slug);
  });

  // Health check for load balancers / k8s probes.
  app.get('/health', async () => ({
    status: 'ok',
    service: 'smart-restaurant-ai-waiter',
    time: new Date().toISOString(),
  }));

  // Root info.
  app.get('/', async () => ({
    service: 'Smart Restaurant AI Waiter Service',
    version: '1.0.0',
    endpoints: { chat: 'POST /api/ai/chat', health: 'GET /health', testUi: 'GET /ui' },
  }));

  // Feature routes.
  app.register(chatRoutes);

  return app;
}

async function start(): Promise<void> {
  const app = buildServer();
  try {
    await app.listen({ port: config.port, host: config.host });
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }

  // Graceful shutdown.
  const shutdown = async (signal: string) => {
    app.log.info(`Received ${signal}, shutting down…`);
    await app.close();
    process.exit(0);
  };
  process.on('SIGINT', () => void shutdown('SIGINT'));
  process.on('SIGTERM', () => void shutdown('SIGTERM'));
}

// Only auto-start when run directly (so tests can import buildServer).
if (require.main === module) {
  void start();
}
