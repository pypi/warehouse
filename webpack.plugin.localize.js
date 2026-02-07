/* SPDX-License-Identifier: Apache-2.0 */

/* This is a webpack plugin.
 * This plugin generates one javascript bundle per locale.
 *
 * It replaces the javascript translation function arguments with the locale-specific data.
 * The javascript functions are in `warehouse/static/js/warehouse/utils/messages-access.js`.
 *
 * Run 'make translations' before webpack to extract the translatable text to gettext format files.
 */

// ref: https://webpack.js.org/contribute/writing-a-plugin/
// ref: https://github.com/zainulbr/i18n-webpack-plugin/blob/v2.0.3/src/index.js
// ref: https://github.com/webpack/webpack/discussions/14956
// ref: https://github.com/webpack/webpack/issues/9992

/* global module, __dirname */

const ConstDependency = require("webpack/lib/dependencies/ConstDependency");
const fs = require("node:fs");
const {resolve} = require("node:path");
const path = require("path");
const gettextParser = require("gettext-parser");

// generate and then load the locale translation data
const baseDir = __dirname;
const localeDir = path.resolve(baseDir, "warehouse/locale");
// This list should match `warehouse.i18n.KNOWN_LOCALES`
const KNOWN_LOCALES = [
  "en",  // English
  "es",  // Spanish
  "fr",  // French
  "ja",  // Japanese
  "pt_BR",  // Brazilian Portuguese
  "uk",  // Ukrainian
  "el",  // Greek
  "de",  // German
  "zh_Hans",  // Simplified Chinese
  "zh_Hant",  // Traditional Chinese
  "ru",  // Russian
  "he",  // Hebrew
  "eo",  // Esperanto
  "ko",  // Korean
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

const allLocaleData = KNOWN_LOCALES
  .filter(langCode => langCode !== "en")
  .map((langCode) => resolve(localeDir, langCode, "LC_MESSAGES/messages.po"))
  .filter((file) => fs.statSync(file).isFile())
  .map((file) => ({path: path.relative(baseDir, file), data: fs.readFileSync(file, "utf8")}))
  .map((data) => {
    try {
      const lines = data.data
        .split("\n")
        // gettext-parser does not support obsolete previous translations,
        // so filter out those lines
        // see: https://github.com/smhg/gettext-parser/issues/79
        .filter(line => !line.startsWith("#~|"))
        .join("\n");
      const parsed = gettextParser.po.parse(lines);
      const language = parsed.headers["Language"];
      const pluralForms = parsed.headers["Plural-Forms"];
      const result = {
        "": {
          "language": language,
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
        if (refs.every(refLine => !refLine.includes(".js:"))) {
          continue;
        }
        result[value.msgid] = value.msgstr.map(function(str) {
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
      throw new Error(`Could not parse file ${data.path}: ${e.message}\n${e}`);
    }
  });


const pluginName = "WebpackLocalisationPlugin";

class WebpackLocalisationPlugin {
  constructor(localeData) {
    this.localeData = localeData || {};
  }

  apply(compiler) {
    const self = this;

    // create a handler for each factory.hooks.parser
    const handler = function (parser) {

      parser.hooks.statement.tap(pluginName, (statement) => {
        if (statement.type === "VariableDeclaration" &&
          statement.declarations.length === 1 &&
          statement.declarations[0].id.name === "messagesAccessLocaleData") {
          const initData = statement.declarations[0].init;
          const dep = new ConstDependency(JSON.stringify(self.localeData), initData.range);
          dep.loc = initData.loc;
          parser.state.current.addDependency(dep);
          return true;

        } else if (statement.type === "VariableDeclaration" &&
          statement.declarations.length === 1 &&
          statement.declarations[0].id.name === "messagesAccessPluralFormFunction") {
          const initData = statement.declarations[0].init;
          const pluralForms = self.localeData[""]["plural-forms"];
          const newValue = `function (n) {
  let nplurals, plural;
  ${pluralForms}
  return {total: nplurals, index: ((nplurals > 1 && plural === true) ? 1 : (plural ? plural : 0))};
}`;
          const dep = new ConstDependency(newValue, initData.range);
          dep.loc = initData.loc;
          parser.state.current.addDependency(dep);
          return true;

        }
      });
    };

    // place the handler into the hooks for the webpack compiler module factories
    compiler.hooks.normalModuleFactory.tap(pluginName, factory => {
      factory.hooks.parser.for("javascript/auto").tap(pluginName, handler);
      factory.hooks.parser.for("javascript/dynamic").tap(pluginName, handler);
      factory.hooks.parser.for("javascript/esm").tap(pluginName, handler);
    });
  }
}

module.exports.WebpackLocalisationPlugin = WebpackLocalisationPlugin;
module.exports.allLocaleData = allLocaleData;
