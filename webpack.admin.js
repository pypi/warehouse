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

// Prefix to our source files
const staticPrefix = "warehouse/admin/static/";
// Absolute path to where the output assets will be saved
const distPath = path.resolve(staticPrefix, "dist");

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
      // Admin bundles JS and CSS into two files, admin.js and all.css
      "js/admin": glob
        .sync(path.join(staticPrefix, "js/*.js"))
        .map(imagePath => path.join(__dirname, imagePath)),
      "css/all": [
        "./css/bootstrap.min.css",
        "./css/fontawesome.min.css",
        "./css/AdminLTE.min.css",
        "./css/skins/skin-purple.min.css",
      ],
    },
  }, baseConfig);
  // Fonts are picked up from CSS files and copied to /admin/static/fonts/
  config.module.rules.pop();
  config.module.rules.push(
    {
      test: /\.(woff2?|ttf|eot|svg)$/i,
      use: [
        {
          loader: "file-loader",
          options: {
            name: "fonts/[name].[contenthash:8].[ext]",
            publicPath: "/admin/static/",
          },
        },
      ],
    },
  );
  config.output.path = distPath;

  return config;
};
