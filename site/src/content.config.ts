import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

export const collections = {
  documents: defineCollection({
    loader: glob({
      base: '..',
      pattern: ['guides/**/*.md', 'agents/**/*.md', 'commands/**/*.md', 'configs/**/*.md'],
      generateId: ({ entry }) => entry,
    }),
    schema: z.looseObject({ title: z.string().optional() }),
  }),
};
