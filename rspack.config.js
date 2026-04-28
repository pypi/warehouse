/* SPDX-License-Identifier: Apache-2.0 */

/* global module, process, __dirname */

// Main configuration file for rspack (webpack-compatible bundler in Rust).
// See: https://rspack.dev/config/

const path = require("path");
const rtlcss = require("rtlcss");
const CssMinimizerPlugin = require("css-minimizer-webpack-plugin");
// TODO: webpack-livereload-plugin is rspack-incompatible. For dev iteration
// today, `bun run watch` rebuilds on file change. To restore live-reload /
// HMR, switch to @rspack/dev-server.
const RemoveEmptyScriptsPlugin = require("webpack-remove-empty-scripts");

const rspack = require("@rspack/core");
const ProvidePlugin = rspack.ProvidePlugin;
const DefinePlugin = rspack.DefinePlugin;
// rspack's native CSS-extract / file-copy plugins (the webpack equivalents
// rely on internals — `mini-css-extract-plugin` taps `registerLoader`,
// `copy-webpack-plugin` hangs in `processAssets` — that rspack does not
// expose).
const MiniCssExtractPlugin = rspack.CssExtractRspackPlugin;
const CopyPlugin = rspack.CopyRspackPlugin;

const ManifestPlugin = require("./rspack.plugin.manifest.js");
const {defineLocaleConstants, allLocaleData} = require("./rspack.plugin.localize.js");

const isDev = process.env.NODE_ENV === "development";

// NOTE: pre-compression (.gz / .br via compression-webpack-plugin) and image
// minification (sharp / svgo via image-minimizer-webpack-plugin) used to run
// inside the bundler; they're now post-build steps invoked from
// bin/static_pipeline because their plugin APIs are not rspack-compatible.
// See npm scripts `compress` and `imagemin` (added in package.json).

/* Shared Plugins */

const sharedCSSPlugins = [
  new MiniCssExtractPlugin({
    // Places CSS into a subdirectory
    filename: "css/[name].[contenthash].css",
  }),
  new RemoveEmptyScriptsPlugin(),
];


// Refs: https://github.com/shellscape/webpack-manifest-plugin/issues/229#issuecomment-737617994
const sharedWebpackManifestPublicPath = "";
const sharedWebpackManifestData = {};
const sharedWebpackManifestMap =
  // Replace each entry with a prefix of a subdirectory.
  // NOTE: This could be removed if we update the HTML to use the non-prefixed
  //       paths.
  (file) => {
    // if the filename matches .js or .js.map, add js/ prefix if not already present
    if (file.name.match(/\.js(\.map)?$/)) {
      if (!file.name.startsWith("js/")) {
        file.name = `js/${file.name}`;
      }
    }
    // if the filename matches .css or .css.map, add a prefix of css/
    if (file.name.match(/\.css(\.map)?$/)) {
      if (!file.name.startsWith("css/")) {
        file.name = `css/${file.name}`;
      }
    }
    return file;
  };

/* End Shared Plugins */

const sharedPerformance = {
  assetFilter: (assetFilename) =>
    // Exclude zxcvbn dictionary chunks — inherently large and loaded async
    !assetFilename.startsWith("zxcvbn") &&
    // Exclude source maps and pre-compressed files — not loaded as page assets
    !/\.(map|gz|br)$/.test(assetFilename),
};

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
            // Copy utility for sanitizing plausible analytics
            from: path.resolve(__dirname, "warehouse/static/js/vendor/plausible-sanitized.js"),
            to: "js/utils/[name].[contenthash][ext]",
          },
        ],
      }),
      ...sharedCSSPlugins,
      new ManifestPlugin({
        removeKeyHash: /([a-f0-9]{8}\.?)/gi,
        publicPath: sharedWebpackManifestPublicPath,
        seed: sharedWebpackManifestData,
        map: sharedWebpackManifestMap,
      }),
      ...isDev ? [
        // Watch HTML templates so LiveReload triggers on template changes.
        {
          apply(compiler) {
            const glob = require("glob");
            compiler.hooks.afterCompile.tap("WatchTemplatesPlugin", (compilation) => {
              for (const pattern of [
                "warehouse/templates/**/*.html",
                "warehouse/admin/templates/**/*.html",
              ]) {
                for (const file of glob.sync(pattern)) {
                  compilation.fileDependencies.add(path.resolve(__dirname, file));
                }
              }
            });
          },
        },
      ] : [],
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

      /* Self-hosted fonts via Fontsource */
      fonts: "./warehouse/static/js/vendor/fonts.js",
      "fonts-ewert": "./warehouse/static/js/vendor/fonts-ewert.js",
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
                {
                  loader: "sass-loader",
                  options: {
                    sassOptions: {
                      loadPaths: [path.resolve(__dirname, "node_modules")],
                    },
                  },
                },
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
                {
                  loader: "sass-loader",
                  options: {
                    sassOptions: {
                      loadPaths: [path.resolve(__dirname, "node_modules")],
                    },
                  },
                },
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
    performance: sharedPerformance,
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
                discardComments: {removeAll: true},
              },
            ],
          },
        }),
        // Image minimization (sharp/svgo) and pre-compression (gzip/brotli)
        // moved to post-build npm scripts — see bin/static_pipeline.
      ],
    },
  },
  {
    name: "admin",
    plugins: [
      ...sharedCSSPlugins,
      new ManifestPlugin({
        removeKeyHash: /([a-f0-9]{8}\.?)/gi,
        publicPath: sharedWebpackManifestPublicPath,
        map: sharedWebpackManifestMap,
      }),
      // admin site dependencies use jQuery
      new ProvidePlugin({
        $: "jquery",
        jQuery: "jquery",
      }),
      // (LiveReload removed — rspack-incompatible; use @rspack/dev-server for HMR)
    ],
    resolve: sharedResolve,
    entry: {
      admin: {
        import: "./warehouse/admin/static/js/warehouse.js",
        filename: "js/admin.[contenthash].js",
      },
      all: {
        import: "./warehouse/admin/static/css/admin.css",
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
          test: /\.(woff|woff2|eot|ttf|otf)$/i,
          type: "asset/resource",
          generator: {
            filename: "fonts/[name].[contenthash][ext]",
          },
        },
      ],
    },
  },
  // for each language locale, generate config for warehouse
  ...allLocaleData.map(function (localeData) {
    const name = `warehouse.${localeData[""].language}`;
    return {
      name: name,
      plugins: [
        new DefinePlugin(defineLocaleConstants(localeData)),
        new ManifestPlugin({
          removeKeyHash: /([a-f0-9]{8}\.?)/gi,
          publicPath: sharedWebpackManifestPublicPath,
          seed: sharedWebpackManifestData,
          map: sharedWebpackManifestMap,
        }),
        // (LiveReload removed — rspack-incompatible; use @rspack/dev-server for HMR)
      ],
      resolve: sharedResolve,
      entry: {
        // Webpack will create a bundle for each entry point.

        /* JavaScript */
        [name]: {
          import: "./warehouse/static/js/warehouse/index.js",
          // override the filename from `index` to `warehouse`
          filename: `js/${name}.[contenthash].js`,
        },
      },
      // The default source map. Slowest, but best production-build optimizations.
      // See: https://webpack.js.org/configuration/devtool
      devtool: "source-map",
      output: {
        // Matches current behavior. Defaults to 20. 16 in the future.
        hashDigestLength: 8,
        // Global filename template for all assets. Other assets MUST override.
        filename: "[name].[contenthash].js",
        // Global output path for all assets.
        path: path.resolve(__dirname, "warehouse/static/dist"),
      },
      performance: sharedPerformance,
      dependencies: ["warehouse"],
      // Emit fewer stats-per-language in non-production builds.
      stats: (process.env.NODE_ENV === "production") ? undefined : "errors-warnings",
    };
  }),
];
