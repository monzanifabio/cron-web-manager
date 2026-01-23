import { resolve } from "path";

export default {
  root: resolve(__dirname),
  build: {
    outDir: "../backend/dist",
    emptyOutDir: true,
  },
  server: {
    host: "0.0.0.0",
    port: 8080,
  },
  // Optional: Silence Sass deprecation warnings. See note below.
  css: {
    preprocessorOptions: {
      scss: {
        silenceDeprecations: ["import", "mixed-decls", "color-functions", "global-builtin"],
      },
    },
  },
};
