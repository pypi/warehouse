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
const webpack = require("webpack");

const { CleanWebpackPlugin } = require("clean-webpack-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const FixStyleOnlyEntriesPlugin = require("webpack-fix-style-only-entries");
const CopyPlugin = require("copy-webpack-plugin");
const TerserPlugin = require("terser-webpack-plugin");
const ManifestPlugin = require("webpack-manifest-plugin");
const CompressionPlugin = require("compression-webpack-plugin");
const OptimizeCSSAssetsPlugin = require("optimize-css-assets-webpack-plugin");

// Configure where our files come from, where they get saved too, and what path
// they are served from.
const staticPrefix = "warehouse/static/";
const distPath = path.resolve(staticPrefix, "dist");
const fontAwesomePath = path.dirname(require.resolve("@fortawesome/fontawesome-free/package.json"));

/* global module, __dirname */

module.exports = (_env, args) => { // eslint-disable-line no-unused-vars
  const config = {
    // Define the context allowing use to use relative paths
    context: path.resolve(__dirname, staticPrefix),
    // Entry points to our frontend code, Webpack will create a dependency
    // graph based on the imports. Note that additional files are emitted
    // in the plugins section. The names of the entry points _must_ match
    // their subdirectory in dist in order for the manifest to match the
    // static URLs in the templates.
    entry: {
      "js/warehouse": "./js/warehouse/index.js",
      "css/warehouse": "./sass/warehouse.scss",
      "css/noscript": "./sass/noscript.scss",
      "images": glob
        .sync(path.join(staticPrefix, "images/**/*"))
        .map(imagePath => path.join(__dirname, imagePath)),
      "css/fontawesome": path.resolve(fontAwesomePath, "css/fontawesome.css"),
      "css/regular": path.resolve(fontAwesomePath, "css/regular.css"),
      "css/solid": path.resolve(fontAwesomePath, "css/solid.css"),
      "css/brands": path.resolve(fontAwesomePath, "css/brands.css"),
    },
    module: {
      rules: [
        {
          test: /\.js$/,
          exclude: /node_modules/,
          use: {
            loader: "babel-loader",
            options: {
              presets: ["@babel/preset-env"],
              plugins: ["@babel/plugin-proposal-class-properties"],
            },
          },
        },
        {
          test: /\.s?css$/,
          loaders: [
            MiniCssExtractPlugin.loader,
            "css-loader",
            "sass-loader",
          ],
        },
        {
          test: /\.(gif|png|jpe?g|svg|ico)$/i,
          use: [
            {
              loader: "file-loader",
              options: {
                name: "images/[name].[contenthash:8].[ext]",
              },
            },
            "image-webpack-loader",
          ],
        },
        {
          test: /\.(woff2?|ttf|eot)$/i,
          use: [
            {
              loader: "file-loader",
              options: {
                name: "webfonts/[name].[contenthash:8].[ext]",
                // Links in CSS files must point to /static/webfonts/
                publicPath: "/static/",
              },
            },
          ],
        },
      ],
    },
    plugins: [
      // Clean the dist/ directory
      new CleanWebpackPlugin(),
      // Inject fetch and jQuery without specifically importing them
      new webpack.ProvidePlugin({
        "fetch": "imports-loader?this=>global!exports-loader?global.fetch!whatwg-fetch",
        "jQuery": "jquery",
        "$": "jquery",
      }),
      // Remove empty .js file created by CSS-only entry points
      // Webpack is a JS first bundler so all entry points emit JS files
      new FixStyleOnlyEntriesPlugin(),
      // Extract the CSS in entry points and emits it separately
      new MiniCssExtractPlugin({
        filename: "[name].[contenthash:8].css",
      }),
      // Copy without processing vendored JS
      new CopyPlugin([
        {
          from: "./js/vendor",
          to: path.join(distPath, "js", "vendor", "[name].[contenthash:8].[ext]"),
        },
      ]),
      // Copy without processing fontawesome webfonts
      new CopyPlugin([
        {
          from: path.join(fontAwesomePath, "webfonts"),
          to: path.join(distPath, "webfonts", "[name].[contenthash:8].[ext]"),
        },
      ]),
      // Create a manifest file
      new ManifestPlugin({
        filter(file) { return !file.name.match(/\.(br|gz)$/); }, // exclude compressed files
      }),
    ],
    devtool: "source-map",  // TODO: consider a faster source map option
    output: {
      path: distPath,
      publicPath: "",
      filename: "[name].[contenthash:8].js",
    },
    resolve: {
      modules: [path.resolve(staticPrefix, "js"), "node_modules"],
      alias: {
        "clipboard": "clipboard/dist/clipboard",
      },
    },
    optimization: {
      minimize: true,
      minimizer: [
        new TerserPlugin({}),
        new OptimizeCSSAssetsPlugin({
          cssProcessorPluginOptions: {
            preset: ["default", { discardComments: { removeAll: true } }],
          },
        }),
      ],
    },
    watchOptions: {
      ignored: ["dist/**", "html/**"],
    },
  };

  if (args.mode === "production") {
    config.plugins.push(
      // Create gzip and brotli compressed versions of our assets
      // Note the default compression ratio is 0.8 which may result
      // in some assets not generating compressed versions, like some PNG files
      new CompressionPlugin({
        test: /\.(js|css|png|jpg|svg|map)$/,
      }),
      new CompressionPlugin({
        filename: "[path].br",
        algorithm: "brotliCompress",
        test: /\.(js|css|png|jpg|svg|map)$/,
      }),
    );
  }

  return config;
};