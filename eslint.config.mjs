import stylisticJs from "@stylistic/eslint-plugin-js";
import globals from "globals";
import path from "node:path";
import { fileURLToPath } from "node:url";
import js from "@eslint/js";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const compat = new FlatCompat({
    baseDirectory: __dirname,
    recommendedConfig: js.configs.recommended,
    allConfig: js.configs.all,
});

export default [{
    ignores: ["static/js/vendor/zxcvbn.js"],
}, ...compat.extends("eslint:recommended"), {
    plugins: {
        "@stylistic/js": stylisticJs,
    },

    languageOptions: {
        globals: {
            ...globals.browser,
            ...globals.amd,
            ...globals.jquery,
        },

        ecmaVersion: "latest",
        sourceType: "module",
    },

    rules: {
         
        "@stylistic/js/comma-dangle": ["error", "always-multiline"],
        "@stylistic/js/indent": ["off"],
        "@stylistic/js/linebreak-style": ["error", "unix"],
        "@stylistic/js/quotes": ["off"],
        "@stylistic/js/semi": ["off"],
    },
}];