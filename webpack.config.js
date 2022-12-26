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
const glob = require("glob");
const CompressionPlugin = require("compression-webpack-plugin");
const CopyPlugin = require("copy-webpack-plugin");
const CssMinimizerPlugin = require("css-minimizer-webpack-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const RemoveEmptyScriptsPlugin = require("webpack-remove-empty-scripts");
const { WebpackManifestPlugin } = require("webpack-manifest-plugin");

// FontAwesome resources helpers for dynamic entry points
const fABasePath = path.dirname(require.resolve("@fortawesome/fontawesome-free/package.json"));
const fACSSPath = path.resolve(fABasePath, "css", "*.css");
// TODO: Do we need to handle the remaining fonts, or are imported-in-CSS sufficient?

module.exports = {
  // TODO: remove and set NODE_ENV during build
  mode: "development",
  plugins: [
    new CopyPlugin({
      patterns: [
        {
          // Most images are not referenced in JS/CSS, copy them manually.
          from: path.resolve(__dirname, "warehouse/static/images/*"),
          to: "images/[name].[contenthash][ext]",
        },
        {
          // Copy vendored zxcvbn code
          from: path.resolve(__dirname, "warehouse/static/js/vendor/zxcvbn.js"),
          to: "js/vendor/[name].[contenthash][ext]",
        },
      ],
    }),
    new MiniCssExtractPlugin({
      // Places CSS into a subdirectory
      filename: "css/[name].[contenthash].css",
    }),
    new RemoveEmptyScriptsPlugin(),
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
    new WebpackManifestPlugin({
      // Replace each entry with a prefix of a subdirectory.
      // NOTE: This could be removed if we update the HTML to use the non-prefixed
      //       paths.
      map: (file) => {
        // if the filename matches .js or .js.map, add js/ prefix if not already present
        if (file.name.match(/\.js(\.map)?$/)) {
          if (!file.name.startsWith("js/")) {
            file.name = `js/${file.name}`; // eslint-disable-line no-param-reassign
          }
        }
        // if the filename matches .css or .css.map, add a prefix of css/
        if (file.name.match(/\.css(\.map)?$/)) {
          file.name = `css/${file.name}`; // eslint-disable-line no-param-reassign
        }
        return file;
      },
      // Refs: https://github.com/shellscape/webpack-manifest-plugin/issues/229#issuecomment-737617994
      publicPath: "",
    }),
  ],
  resolve: {
    alias: {
      // Use an alias to make inline non-relative `@import` statements.
      warehouse: path.resolve(__dirname, "warehouse/static/js/warehouse"),
    },
  },
  entry: {
    // Webpack will create a bundle for each entry point.

    /* JavaScript */
    warehouse: {
      import: "./warehouse/static/js/warehouse/index.js",
      // override the filename from `index` to `warehouse`
      filename: "js/warehouse.[contenthash].js",
    },

    /* CSS */
    noscript: "./warehouse/static/sass/noscript.scss",
    // Fontawesome is a special case, as it's many CSS files in a npm package.
    // OPTIMIZE: Determine which ones we actually use, and import them directly.
    ...glob.sync(fACSSPath).reduce((acc, curr) => {
      return { ...acc, [path.basename(curr, ".css")]: curr };
    }, {}),

    // Default CSS
    "warehouse-ltr": "./warehouse/static/sass/warehouse.scss",
    // TODO: add RTL CSS
  },
  // The default source map. Slowest, but best production-build optimizations.
  // See: https://webpack.js.org/configuration/devtool
  devtool: "source-map",
  output: {
    // remove old files
    clean: true,
    // Matches current behavior. Defaults to 20. 16 in the future.
    hashDigestLength: 8,
    // Global filename template for all assets. Other assets MUST override.
    filename: "[name].[contenthash].js",
    // Global output path for all assets.
    path: path.resolve(__dirname, "warehouse/static/dist"),
  },
  module: {
    rules: [
      {
        // Handle SASS/SCSS files
        test: /\.s[ac]ss$/i,
        use: [
          // Extracts CSS into separate files
          MiniCssExtractPlugin.loader,
          // Translates CSS into CommonJS,
          "css-loader",
          // Translate SCSS to CSS
          "sass-loader",
        ],
      },
      {
        // Handle CSS files
        test: /\.css$/,
        use: [
          MiniCssExtractPlugin.loader,
          "css-loader",
        ],
      },
      {
        // Handle image files
        test: /\.(png|svg|jpg|jpeg|gif)$/i,
        // disables data URL inline encoding images into CSS,
        // since it violates our CSP settings.
        type: "asset/resource",
        generator: {
          filename: "images/[name].[contenthash][ext]",
        },
      },
      {
        // Handle font files
        test: /\.(woff|woff2|eot|ttf|otf)$/i,
        type: "asset/resource",
        generator: {
          filename: "webfonts/[name].[contenthash][ext]",
        },
      },
    ],
  },
  optimization: {
    minimizer: [
      // default minimizer is Terser for JS. Extend here vs overriding.
      "...",
      // Minimize CSS
      new CssMinimizerPlugin({
        minimizerOptions: {
          preset: [
            "default",
            {
              discardComments: { removeAll: true },
            },
          ],
        },
      }),
    ],
  },
};
