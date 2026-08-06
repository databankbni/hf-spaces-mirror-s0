import { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import { ChatRequestSchema } from '../types';
import { aiService } from '../services/ai.service';
import { MenuFetchError } from '../services/menu.service';

/**
 * Chat Controller
 * ---------------
 * Exposes POST /api/ai/chat. Validates the request with Zod, delegates to the
 * AiService, and maps domain errors to clean HTTP responses. Never leaks raw
 * JSON menu data outside the documented `results` field.
 */

interface ErrorBody {
  error: string;
  detail?: string;
}

export async function chatRoutes(app: FastifyInstance): Promise<void> {
  app.post(
    '/api/ai/chat',
    async (request: FastifyRequest, reply: FastifyReply) => {
      // 1. Validate input.
      const parsed = ChatRequestSchema.safeParse(request.body);
      if (!parsed.success) {
        const body: ErrorBody = {
          error: 'Invalid request.',
          detail: parsed.error.issues
            .map((i) => `${i.path.join('.') || 'body'}: ${i.message}`)
            .join('; '),
        };
        return reply.code(400).send(body);
      }

      const { restaurantSlug, message, sessionId } = parsed.data;

      // 2. Run the waiter pipeline.
      try {
        const result = await aiService.handleChat(restaurantSlug, message, sessionId);
        return reply.code(200).send(result);
      } catch (err) {
        if (err instanceof MenuFetchError) {
          // Surface a friendly, waiter-style message even on backend failure.
          request.log.warn(
            { slug: err.slug, status: err.status, msg: err.message },
            'menu fetch failed',
          );
          const friendly =
            err.status === 404
              ? "I'm sorry, I couldn't find that restaurant. Please check the link and try again."
              : "I'm sorry, I'm having trouble reaching the kitchen right now. Please try again shortly.";

          return reply.code(err.status === 404 ? 404 : 502).send({
            sessionId: sessionId ?? '',
            intent: 'unknown',
            confidence: 0,
            results: [],
            reply: friendly,
            suggestions: ['Would you like to try again?'],
            engine: 'rules',
          });
        }

        request.log.error({ err }, 'unexpected error in chat pipeline');
        const body: ErrorBody = { error: 'Internal server error.' };
        return reply.code(500).send(body);
      }
    },
  );
}
