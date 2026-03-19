/* SPDX-License-Identifier: Apache-2.0 */
import js from "@eslint/js";
import globals from "globals";
import stylisticJs from "@stylistic/eslint-plugin-js";

export default [
  {
    ignores: ["warehouse/static/js/vendor/**"],
  },
  {
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.amd,
        ...globals.jquery,
      },
    },
    plugins: {
      "@stylistic/js": stylisticJs,
    },
    rules: {
      ...js.configs.recommended.rules,
      "@stylistic/js/comma-dangle": ["error", "always-multiline"],
      "@stylistic/js/indent": ["error", 2],
      "@stylistic/js/linebreak-style": ["error", "unix"],
      "@stylistic/js/quotes": ["error", "double"],
      "@stylistic/js/semi": ["error", "always"],
      "no-unused-vars": ["error", { "argsIgnorePattern": "^_" }],
    },
  },
];
