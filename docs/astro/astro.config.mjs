import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

export default defineConfig({
  site: 'https://max-models.github.io',
  base: '/strava-collections',
  integrations: [tailwind()],
  markdown: {
    remarkRehypeOptions: {
      allowDangerousHtml: true,
    },
  },
});
