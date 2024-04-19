/* Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/* This is a webpack plugin.
 *
 * This plugin generates one javascript bundle per locale.
 * It replaces the javascript translation function arguments with the locale-specific data.
 *
 * gettext.js is then used to determine the translation to use and replace placeholders.
 * The javascript functions are in `warehouse/static/js/warehouse/utils/messages-access.js`.
 *
 * Run 'make translations' to generate the 'messages.json' files for the KNOWN_LOCALES.
 */

// ref: https://webpack.js.org/contribute/writing-a-plugin/
// ref: https://github.com/zainulbr/i18n-webpack-plugin/blob/v2.0.3/src/index.js
// ref: https://github.com/webpack/webpack/discussions/14956
// ref: https://github.com/webpack/webpack/issues/9992

const ConstDependency = require("webpack/lib/dependencies/ConstDependency");
const fs = require("node:fs");
const {resolve} = require("node:path");
const path = require("path");

// load the locale translation data
const baseDir = path.resolve(__dirname, "warehouse/locale");
const localeData = fs.readdirSync(baseDir)
  .map((file) => resolve(baseDir, file, "LC_MESSAGES/messages.json"))
  .filter((file) => {
    try {
      return fs.statSync(file).isFile();
    } catch {
    }
  })
  .map((file) => {
    console.log(`Translations from ${path.relative(__dirname, file)}`);
    return fs.readFileSync(file, "utf8");
  })
  .map((data) => JSON.parse(data));

// TODO: don't allow changing the WebpackLocalisationPlugin.functions - just do what is needed
const defaultFunctionGetTextJs = function (data, singular) {
  let value;
  if (Object.hasOwn(data.entries, singular)) {
    value = JSON.stringify({
      "singular": singular,
      "data": {
        "": {
          "locale": data.locale,
          "plural-forms": data["plural-forms"],
        },
        [singular]: Object.entries(data.entries[singular].msgstr_plural).map((entry) => entry[1]),
      },
    });
  } else {
    value = `"${singular}"`;
  }
  return value;
};
const defaultFunctionExtras = function (extras) {
  let extrasString = "";
  if (extras.length > 0) {
    extrasString = `, "${extras.join("\", \"")}"`;
  }
  return extrasString;
};
const defaultFunctions = {
  gettext: (data, singular, ...extras) => {
    const value = defaultFunctionGetTextJs(data, singular);
    const extrasString = defaultFunctionExtras(extras);
    return `gettext(${value} ${extrasString})`;
  },
  ngettext: (data, singular, plural, num, ...extras) => {
    const value = defaultFunctionGetTextJs(data, singular);
    const extrasString = defaultFunctionExtras(extras);
    return `ngettext(${value}, "${plural}", ${num} ${extrasString})`;
  },
};

class WebpackLocalisationPlugin {
  constructor(options) {
    const opts = options || {};
    this.localeData = opts.localeData || {};
    this.functions = opts.functions || defaultFunctions;
  }

  apply(compiler) {
    const pluginName = "WebpackLocalisationPlugin";
    const self = this;

    // create a handler for each factory.hooks.parser
    const handler = function (parser) {

      // for each function name and processing function
      Object.keys(self.functions).forEach(function (findFuncName) {
        const pluginTagImport = Symbol(`${pluginName}-import-tag-${findFuncName}`);
        const replacementFunction = self.functions[findFuncName];

        // tag imports so can later hook into their usages
        parser.hooks.importSpecifier.tap(pluginName, (statement, source, exportName, identifierName) => {
          if (exportName === findFuncName && identifierName === findFuncName) {
            parser.tagVariable(identifierName, pluginTagImport, {});
            return true;
          }
        });

        // hook into calls of the tagged imported function
        parser.hooks.call.for(pluginTagImport).tap(pluginName, expr => {
          try {
            // pass the appropriate information for each type of argument
            // TODO: pass expr.arguments directly so the information is available
            let replacementValue = replacementFunction(self.localeData, ...expr.arguments.map((argument) => {
              if (argument.type === "Literal") {
                return argument.value;
              } else if (argument.type === "Identifier") {
                return argument.name;
              } else {
                throw new Error(`Unknown argument type '${argument.type}'.`);
              }
            }));
            const dep = new ConstDependency(replacementValue, expr.range);
            dep.loc = expr.loc;
            parser.state.current.addDependency(dep);
            return true;
          } catch (err) {
            parser.state.module.errors.push(err);
          }
        });

      });
    };

    // place the hooks into the webpack compiler, factories
    compiler.hooks.normalModuleFactory.tap(pluginName, factory => {
      factory.hooks.parser.for("javascript/auto").tap(pluginName, handler);
      factory.hooks.parser.for("javascript/dynamic").tap(pluginName, handler);
      factory.hooks.parser.for("javascript/esm").tap(pluginName, handler);
    });

  }
}

module.exports.WebpackLocalisationPlugin = WebpackLocalisationPlugin;
module.exports.localeData = localeData;
