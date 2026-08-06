'use client';

import { getTemplateComponent } from '@/templates';
import type { InviteContent } from '@/types/content';

/**
 * Renders the same template component the public invite page uses, hydrated with
 * the editor's current in-progress content — so the buyer sees exactly what
 * guests will see. Scaled inside a phone frame (guests mostly open on mobile).
 */
export function LivePreview({ content }: { content: InviteContent }) {
  const TemplateComponent = getTemplateComponent(content.templateSlug);
  return (
    <div className="overflow-hidden rounded-[2rem] border-8 border-black/80 shadow-xl">
      <div className="h-[640px] overflow-y-auto bg-white">
        <TemplateComponent content={content} />
      </div>
    </div>
  );
}
