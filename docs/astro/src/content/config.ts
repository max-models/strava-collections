import { defineCollection, z } from 'astro:content';

const collectionsConfig = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
  }),
});

export const collections = { collections: collectionsConfig };
