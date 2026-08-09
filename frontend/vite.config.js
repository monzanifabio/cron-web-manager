import { resolve, dirname } from "path";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

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
    proxy: {
      "/api": "http://localhost:8000",
    },
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
