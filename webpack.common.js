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

/**
 * Base for Webpack configurations.
 *
 * Subconfigurations should import and call this function and amend is as
 * necessary, typically defining entry points and output paths.
 * The loaders for JS, CSS, fonts, and images are shared and defined here.
 */


const path = require("path");
const webpack = require("webpack");

const { CleanWebpackPlugin } = require("clean-webpack-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const FixStyleOnlyEntriesPlugin = require("webpack-fix-style-only-entries");
const TerserPlugin = require("terser-webpack-plugin");
const ManifestPlugin = require("webpack-manifest-plugin");
const CompressionPlugin = require("compression-webpack-plugin");
const OptimizeCSSAssetsPlugin = require("optimize-css-assets-webpack-plugin");

const staticPrefix = "warehouse/static/";

/* global module */

module.exports = (_env, args) => { // eslint-disable-line no-unused-vars
  const config = {
    module: {
      rules: [
        {
          test: /\.js$/,
          exclude: /(node_modules|js\/vendor)/,
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
                publicPath: "/static/",
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
      // Create a manifest file, this plugin should appear last
      new ManifestPlugin({
        filter(file) { return !file.name.match(/\.(br|gz)$/); }, // exclude compressed files
      }),
    ],
    devtool: "source-map",  // TODO: consider a faster source map option
    output: {
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
