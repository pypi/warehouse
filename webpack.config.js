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
const rtlcss = require("rtlcss");
const CompressionPlugin = require("compression-webpack-plugin");
const CopyPlugin = require("copy-webpack-plugin");
const CssMinimizerPlugin = require("css-minimizer-webpack-plugin");
const ImageMinimizerPlugin = require("image-minimizer-webpack-plugin");
const LiveReloadPlugin = require('webpack-livereload-plugin');
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const ProvidePlugin = require("webpack").ProvidePlugin;
const RemoveEmptyScriptsPlugin = require("webpack-remove-empty-scripts");
const { WebpackManifestPlugin } = require("webpack-manifest-plugin");

/* Shared Plugins */

const sharedCompressionPlugins = [
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
];

const sharedCSSPlugins = [
  new MiniCssExtractPlugin({
    // Places CSS into a subdirectory
    filename: "css/[name].[contenthash].css",
  }),
  new RemoveEmptyScriptsPlugin(),
];

const sharedWebpackManifestPlugins = [
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
];

/* End Shared Plugins */

const sharedResolve = {
  alias: {
  // Use an alias to make inline non-relative `@import` statements.
    warehouse: path.resolve(__dirname, "warehouse/static/js/warehouse"),
  },
};

module.exports = [
  {
    name: "warehouse",
    experiments: {
    // allow us to manage RTL CSS as a separate file
      layers: true,
    },
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
      ...sharedCompressionPlugins,
      ...sharedCSSPlugins,
      ...sharedWebpackManifestPlugins,
      new LiveReloadPlugin(),
    ],
    resolve: sharedResolve,
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

      // Default CSS
      "warehouse-ltr": "./warehouse/static/sass/warehouse.scss",
      // NOTE: Duplicate RTL CSS target. There's no clean way to generate both
      //       without duplicating the entry point right now.
      "warehouse-rtl": {
        import: "./warehouse/static/sass/warehouse.scss",
        layer: "rtl",
      },

      /* Vendor Stuff */
      fontawesome: "./warehouse/static/sass/vendor/fontawesome.scss",
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
        // Handle SASS/SCSS/CSS files
          test: /\.(sa|sc|c)ss$/,
          // NOTE: Order is important here, as the first match wins
          oneOf: [
            {
            // For the `rtl` file, needs postcss processing
              layer: "rtl",
              issuerLayer: "rtl",
              use: [
                MiniCssExtractPlugin.loader,
                "css-loader",
                {
                  loader: "postcss-loader",
                  options: {
                    postcssOptions: {
                      plugins: [rtlcss()],
                    },
                  },
                },
                "sass-loader",
              ],
            },
            {
            // All other CSS files
              use: [
              // Extracts CSS into separate files
                MiniCssExtractPlugin.loader,
                // Translates CSS into CommonJS
                "css-loader",
                // Translate SCSS to CSS
                "sass-loader",
              ],
            },
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
        // Minimize Images when `mode` is `production`
        new ImageMinimizerPlugin({
          test: /\.(png|jpg|jpeg|gif)$/i,
          minimizer: {
            implementation: ImageMinimizerPlugin.sharpMinify,
          },
          generator: [
            {
            // Apply generator for copied assets
              type: "asset",
              implementation: ImageMinimizerPlugin.sharpGenerate,
              options: {
                encodeOptions: {
                  webp: {
                    quality: 90,
                  },
                },
              },
            },
          ],
        }),
        new ImageMinimizerPlugin({
          test: /\.(svg)$/i,
          minimizer: {
            implementation: ImageMinimizerPlugin.svgoMinify,
            options: {
              encodeOptions: {
                // Pass over SVGs multiple times to ensure all optimizations are applied. False by default
                multipass: true,
                plugins: [
                  // set of built-in plugins enabled by default
                  // see: https://github.com/svg/svgo#default-preset
                  "preset-default",
                ],
              },
            },
          },
        }),
      ],
    },
  },
  {
    name: "admin",
    plugins: [
      ...sharedCompressionPlugins,
      ...sharedCSSPlugins,
      ...sharedWebpackManifestPlugins,
      // admin site dependencies use jQuery
      new ProvidePlugin({
        $: "jquery",
        jQuery: "jquery",
      }),
      new LiveReloadPlugin(),
    ],
    resolve: sharedResolve,
    entry: {
      admin: {
        import: "./warehouse/admin/static/js/warehouse.js",
        filename: "js/admin.[contenthash].js",
      },
      all: {
        import: "./warehouse/admin/static/css/admin.scss",
      },
    },
    devtool: "source-map",
    output: {
      clean: true,
      hashDigestLength: 8,
      filename: "[name].[contenthash].js",
      path: path.resolve(__dirname, "warehouse/admin/static/dist"),
    },
    module: {
      rules: [
        {
          test: /\.(sa|sc|c)ss$/,
          use: [
            MiniCssExtractPlugin.loader,
            "css-loader",
            "sass-loader",
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
          test: /\.(woff|woff2|eot|ttf|otf)$/i,
          type: "asset/resource",
          generator: {
            filename: "fonts/[name].[contenthash][ext]",
          },
        },
      ],
    },
  },
];
