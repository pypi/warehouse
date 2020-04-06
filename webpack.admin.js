/**
 * Licensed under the Apache License, Version 2.0 (the "License");
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

const path = require("path");
const glob = require("glob");

const CopyPlugin = require("copy-webpack-plugin");

// Configure where our files come from, where they get saved too, and what path
// they are served from.
const staticPrefix = "warehouse/admin/static/";
const distPath = path.resolve(staticPrefix, "dist");
const fontAwesomePath = path.dirname(require.resolve("@fortawesome/fontawesome-free/package.json"));
const commonConfig = require("./webpack.common");

/* global module, __dirname */

module.exports = (_env, args) => { // eslint-disable-line no-unused-vars
  const baseConfig = commonConfig(_env, args);
  const config = Object.assign({
    // Define the context allowing use to use relative paths
    context: path.resolve(__dirname, staticPrefix),
    // Entry points to our frontend code, Webpack will create a dependency
    // graph based on the imports. Note that additional files are emitted
    // in the plugins section. The names of the entry points _must_ match
    // their subdirectory in dist in order for the manifest to match the
    // static URLs in the templates.
    entry: {
      "js/admin": glob
        .sync(path.join(staticPrefix, "js/*.js"))
        .map(imagePath => path.join(__dirname, imagePath)),
      // "css/warehouse": "./sass/warehouse.scss",
      // "css/noscript": "./sass/noscript.scss",
      // "images": glob
      //   .sync(path.join(staticPrefix, "images/**/*"))
      //   .map(imagePath => path.join(__dirname, imagePath)),
      // "css/fontawesome": path.resolve(fontAwesomePath, "css/fontawesome.css"),
      // "css/regular": path.resolve(fontAwesomePath, "css/regular.css"),
      // "css/solid": path.resolve(fontAwesomePath, "css/solid.css"),
      // "css/brands": path.resolve(fontAwesomePath, "css/brands.css"),
    },
  }, baseConfig);
  // Make sure the manifest plugin is at the end
  // const manifestPlugin = config.plugins.pop();
  // config.plugins.push(
  //   // Copy without processing vendored JS
  //   new CopyPlugin([
  //     {
  //       from: "./js/vendor/",
  //       to: "./js/vendor/",
  //     },
  //   ]),
  //   // Copy without processing fontawesome webfonts
  //   new CopyPlugin([
  //     {
  //       from: path.join(fontAwesomePath, "webfonts"),
  //       to: "./webfonts/",
  //     },
  //   ]),
  //   manifestPlugin,
  // );
  config.output.path = distPath;

  return config;
};