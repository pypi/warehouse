/* SPDX-License-Identifier: Apache-2.0 */

/* Locale data loader for the bundler.
 *
 * Reads .po files for each known locale, parses translations, and exposes a
 * helper (`defineLocaleConstants`) that returns the DefinePlugin arguments
 * needed to inline that locale's data into the bundle at build time.
 *
 * The actual substitution happens via webpack's standard DefinePlugin (no
 * custom AST plugin) — see the consuming `webpack.config.js` for usage.
 *
 * Run 'make translations' before bundling to extract translatable text into
 * gettext .po files.
 */

/* global module, __dirname */

const fs = require("node:fs");
const { resolve } = require("node:path");
const path = require("path");
const gettextParser = require("gettext-parser");

// generate and then load the locale translation data
const baseDir = __dirname;
const localeDir = path.resolve(baseDir, "warehouse/locale");
// This list should match `warehouse.i18n.KNOWN_LOCALES`
const KNOWN_LOCALES = [
  "en", // English
  "es", // Spanish
  "fr", // French
  "ja", // Japanese
  "pt_BR", // Brazilian Portuguese
  "uk", // Ukrainian
  "el", // Greek
  "de", // German
  "zh_Hans", // Simplified Chinese
  "zh_Hant", // Traditional Chinese
  "ru", // Russian
  "he", // Hebrew
  "eo", // Esperanto
  "ko", // Korean
];

// A custom regular expression to do some basic checking of the plural form,
// to try to ensure the plural form expression contains only expected characters.
// - the plural form expression MUST NOT have any type of quotes and
//   the only whitespace allowed is space (not tab or form feed)
// - MUST NOT allow brackets other than parentheses (()),
//   as allowing braces ({}) might allow ending the function early
// - MUST allow space, number variable (n), numbers, groups (()),
//   comparisons (<>!=), ternary expressions (?:), and/or (&|),
//   remainder (%)
const pluralFormPattern = new RegExp("^ *nplurals *= *[0-9]+ *; *plural *=[ n0-9()<>!=?:&|%]+;?$");

const allLocaleData = KNOWN_LOCALES.filter((langCode) => langCode !== "en")
  .map((langCode) => resolve(localeDir, langCode, "LC_MESSAGES/messages.po"))
  .filter((file) => fs.statSync(file).isFile())
  .map((file) => ({ path: path.relative(baseDir, file), data: fs.readFileSync(file, "utf8") }))
  .map((data) => {
    try {
      const lines = data.data
        .split("\n")
        // gettext-parser does not support obsolete previous translations,
        // so filter out those lines
        // see: https://github.com/smhg/gettext-parser/issues/79
        .filter((line) => !line.startsWith("#~|"))
        .join("\n");
      const parsed = gettextParser.po.parse(lines);
      const language = parsed.headers["Language"];
      const pluralForms = parsed.headers["Plural-Forms"];
      const result = {
        "": {
          language: language,
          "plural-forms": pluralForms,
        },
      };

      if (!pluralFormPattern.test(pluralForms)) {
        throw new Error(`Invalid plural forms for '${language}': "${pluralForms}"`);
      }

      const translations = parsed.translations[""];
      for (const key in translations) {
        if (key === "") {
          continue;
        }
        const value = translations[key];
        const refs = value.comments.reference.split("\n");
        if (refs.every((refLine) => !refLine.includes(".js:"))) {
          continue;
        }
        result[value.msgid] = value.msgstr.map(function (str) {
          return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
        });
      }
      return result;
    } catch (e) {
      throw new Error(`Could not parse file ${data.path}: ${e.message}\n${e}`, { cause: e });
    }
  });

/**
 * Build the DefinePlugin definitions for a given locale's data.
 *
 * The returned object plugs straight into `new DefinePlugin({...})`:
 *
 *   __WAREHOUSE_LOCALE_DATA__   — replaced with the JSON-stringified locale
 *                                  translation map (object literal in source).
 *   __WAREHOUSE_PLURAL_FORM_FN__ — replaced with a stringified function
 *                                  literal whose body uses the locale's
 *                                  Plural-Forms expression.
 *
 * `messages-access.js` reads both via a `typeof X !== "undefined"` guard so
 * it remains importable in plain Node / jest, where DefinePlugin doesn't run.
 */
function defineLocaleConstants(localeData) {
  const pluralForms = localeData[""]["plural-forms"];
  const pluralFormFnSource = `(function (n) {
  let nplurals, plural;
  ${pluralForms}
  return {total: nplurals, index: ((nplurals > 1 && plural === true) ? 1 : (plural ? plural : 0))};
})`;
  return {
    __WAREHOUSE_LOCALE_DATA__: JSON.stringify(localeData),
    __WAREHOUSE_PLURAL_FORM_FN__: pluralFormFnSource,
  };
}

module.exports.defineLocaleConstants = defineLocaleConstants;
module.exports.allLocaleData = allLocaleData;
