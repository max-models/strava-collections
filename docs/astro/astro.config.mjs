import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

export default defineConfig({
  integrations: [tailwind()],
  markdown: {
    remarkRehypeOptions: {
      allowDangerousHtml: true,
    },
  },
});
