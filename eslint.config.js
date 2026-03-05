const path = require("path");

module.exports = [
  {
    ignores: [
      "warehouse/static/js/vendor/**",
      "node_modules/**",
      "**/node_modules/**",
      "dist/**",
      "coverage/**",
    ],
  },
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        browser: true,
        es6: true,
        amd: true,
        jquery: true,
        node: true,
      },
    },
    plugins: {
      "@stylistic/js": require("@stylistic/eslint-plugin-js"),
    },
    rules: {
      "@stylistic/js/comma-dangle": ["error", "always-multiline"],
      "@stylistic/js/indent": ["error", 2],
      "@stylistic/js/linebreak-style": ["error", "unix"],
      "@stylistic/js/quotes": ["error", "double"],
      "@stylistic/js/semi": ["error", "always"],
    },
  },
];
