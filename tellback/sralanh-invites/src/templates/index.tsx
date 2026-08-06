import type { ComponentType } from 'react';
import type { TemplateProps } from '@/types/content';
import ModernMinimalist from './ModernMinimalist';
import TraditionalKhmer from './TraditionalKhmer';
import FloralRomantic from './FloralRomantic';

/**
 * Registry mapping a template slug to its renderer. The invite page & preview
 * look up the component here and hydrate it with the invite's content JSON.
 */
const REGISTRY: Record<string, ComponentType<TemplateProps>> = {
  'modern-minimalist': ModernMinimalist,
  'traditional-khmer': TraditionalKhmer,
  'floral-romantic': FloralRomantic
};

export function getTemplateComponent(slug: string): ComponentType<TemplateProps> {
  // Fall back to Modern Minimalist so a bad/legacy slug still renders.
  return REGISTRY[slug] ?? ModernMinimalist;
}
