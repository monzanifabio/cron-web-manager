import js from "@eslint/js";
import prettierConfig from "eslint-config-prettier";

export default [
  js.configs.recommended,
  prettierConfig,
  {
    rules: {
      "no-unused-vars": "warn",
      "no-console": "warn",
    },
  },
];
