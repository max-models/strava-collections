import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://max-models.github.io",
  base: "/strava-collections",
  markdown: {
    remarkRehypeOptions: {
      allowDangerousHtml: true,
    },
  },
});
