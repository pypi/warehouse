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
 * Run `make static_pipeline` to generate the js bundle for each locale.
 *
 * Currently only for 'warehouse', but can be extended to 'admin' if needed.
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
const baseDir = __dirname;
const localeDir = path.resolve(baseDir, "warehouse/locale");
const allLocaleData = fs
  .readdirSync(localeDir)
  .map((file) => resolve(localeDir, file, "LC_MESSAGES/messages.json"))
  .filter((file) => {
    try {
      return fs.statSync(file).isFile();
    } catch {
      // ignore error
    }
  })
  .map((file) => {
    console.log(`Translations from ${path.relative(baseDir, file)}`);
    return fs.readFileSync(file, "utf8");
  })
  .map((data) => JSON.parse(data));


const pluginName = "WebpackLocalisationPlugin";

class WebpackLocalisationPlugin {
  constructor(localeData) {
    this.localeData = localeData || {};
  }

  apply(compiler) {
    const self = this;

    // TODO: how to replace one argument of a function, and keep everything else the same?

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
