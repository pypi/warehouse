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

// This is the main configuration file for webpack.
// See: https://webpack.js.org/configuration/

const path = require("path");
const zlib = require("zlib");
const CompressionPlugin = require("compression-webpack-plugin");

module.exports = {
  // TODO: remove and set NODE_ENV during build
  mode: "development",
  plugins: [
    new CompressionPlugin({
      filename: "[path][base].gz",
      algorithm: "gzip",
      compressionOptions: { level: 9, memLevel: 9 },
      // Only compress files that will actually be smaller when compressed.
      minRatio: 1,
    }),
    /* TODO: Add plugins to compress brotli for text/font files vs the generic
             Use BROTLI_MODE_TEXT/BROTLI_MODE_FONT and add a `test` qualifier. */
    new CompressionPlugin({
      filename: "[path][base].br",
      algorithm: "brotliCompress",
      compressionOptions: {
        params: {
          [zlib.constants.BROTLI_PARAM_QUALITY]: 11,
        },
      },
      // Only compress files that will actually be smaller when compressed.
      minRatio: 1,
    }),
  ],
  resolve: {
    alias: {
      // Use an alias to make inline non-relative `@import` statements.
      warehouse: path.resolve(__dirname, "warehouse/static/js/warehouse"),
    },
  },
  entry: {
    warehouse: "./warehouse/static/js/warehouse/index.js",
    zxcvbn: {
      import: "./warehouse/static/js/vendor/zxcvbn.js",
      filename: "vendor/[name].[contenthash].js",
    },
  },
  // The default source map. Slowest, but best production-build optimizations.
  // See: https://webpack.js.org/configuration/devtool
  devtool: "source-map",
  output: {
    // remove old files
    clean: true,
    // Matches current behavior. Defaults to 20. 16 in the future.
    hashDigestLength: 8,
    filename: "[name].[contenthash].js",
    // Global output path for all assets.
    path: path.resolve(__dirname, "warehouse/static/dist"),
  },
};
