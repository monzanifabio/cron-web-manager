import { resolve } from "path";
import { readFileSync } from "fs";

// Read version from package.json
const pkg = JSON.parse(readFileSync(resolve(__dirname, "package.json"), "utf-8"));
const appVersion = pkg.version;

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
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
};
