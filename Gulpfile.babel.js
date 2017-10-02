import brotli from "gulp-brotli";
import del from "del";
import gulp from "gulp";
import gulpBatch from "gulp-batch";
import gulpCSSNano from "gulp-cssnano";
import gulpImage from "gulp-image";
import gulpSass from "gulp-sass";
import gulpSequence  from "gulp-sequence";
import gulpUglify from "gulp-uglify/minifier";
import gulpWatch from "gulp-watch";
import gulpWebpack  from "webpack-stream";
import gzip from "gulp-gzip";
import manifest from "gulp-rev-all";
import manifestClean from "gulp-rev-napkin";
import named from "vinyl-named";
import path from "path";
import sourcemaps from "gulp-sourcemaps";
import * as uglify from "uglify-js";
import webpack from "webpack";


// Configure where our files come from, where they get saved too, and what path
// they are served from.
let staticPrefix = "warehouse/static/";
let distPath = path.join(staticPrefix, "dist");
let publicPath = "/static/";


// Configure webpack so that it compiles all of our javascript into a bundle.
let webpackConfig = {
  module: {
    loaders: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        loaders: [
          { loader: "babel-loader", query: { presets: ["es2015"] } },
        ],
      },
    ],
  },
  plugins: [
    new webpack.ProvidePlugin({
      "fetch": "imports-loader?this=>global!exports-loader?global.fetch!whatwg-fetch",
    }),
  ],
  // We tell it to use an inline source map, but only so that it can be loaded
  // by gulp-sourcemaps later on. It will actually be written out to disk and
  // *NOT* inlined when all is said and done.
  devtool: "inline-source-map",
  output: {
    publicPath: publicPath + "js/",
    filename: "[name].js",
    chunkFilename: "chunks/[chunkhash].js",
  },
  resolve: {
    modules: [ path.resolve(staticPrefix, "js"), "node_modules" ],
    alias: {
      "clipboard": "clipboard/dist/clipboard",
    },
  },
};


gulp.task("dist:js", () => {
  let files = [
    path.join(staticPrefix, "js", "warehouse", "index.js"),
    path.join(staticPrefix, "js", "pwmask", "pw-mask-toggle.js"),
  ];

  return gulp.src(files)
              // .pipe(named(() => { return "warehouse"; }))
              .pipe(named((file) => {
                // Get the filename that is relative to our js directory
                let relPath = path.relative(
                  path.join(staticPrefix, "js"),
                  file.path
                );
                // If this is our main application, then we want to call it
                // just "warehouse". If this is the password unmasking code
                // we'll call it "pwmask"; much easier to type. otherwise, we'll
                // use whatever the real name is.
                if (relPath == "warehouse/index.js") { return "warehouse"; }
                else if (relPath == "pwmask/pw-mask-toggle.js") { return "pwmask"; }
                else { return path.parse(relPath).name; }
              }))
              .pipe(gulpWebpack(webpackConfig, webpack))
              .pipe(sourcemaps.init({ loadMaps: true }))
                .pipe(gulpUglify(
                  // We don't care about IE6-8 so there's no reason to have
                  // uglify contain to maintain compatability for it.
                  {compress: { screw_ie8: true }, mangle: { screw_ie8: true }},
                  // We pass in our own uglify instance rather than allow
                  // gulp-uglify to use it's own. This makes the usage slightly
                  // more complicated, however it means that we have explicit
                  // control over the exact version of uglify-js used.
                  uglify
                ))
              .pipe(sourcemaps.write("."))
              .pipe(gulp.dest(path.join(distPath, "js")));
});


gulp.task("dist:css", () => {
  let sassPath = path.join(staticPrefix, "sass");

  return gulp.src(path.join(sassPath, "warehouse.scss"))
              .pipe(sourcemaps.init())
                .pipe(
                  gulpSass({ includePaths: [sassPath] })
                    .on("error", gulpSass.logError))
                .pipe(gulpCSSNano({
                  safe: true,
                  discardComments: {removeAll: true},
                }))
              .pipe(sourcemaps.write("."))
              .pipe(gulp.dest(path.join(distPath, "css")));
});


gulp.task("dist:font-awesome:css", () => {
  let fABasePath = path.dirname(require.resolve("font-awesome/package.json")); // eslint-disable-line no-undef
  let fACSSPath = path.resolve(fABasePath, "css", "font-awesome.css");

  return gulp.src(fACSSPath)
              .pipe(sourcemaps.init({ loadMaps: true }))
                .pipe(gulpCSSNano({
                  safe: true,
                  discardComments: {removeAll: true},
                }))
              .pipe(sourcemaps.write("."))
              .pipe(gulp.dest(path.join(distPath, "css")));
});

gulp.task("dist:font-awesome:fonts", () => {
  let fABasePath = path.dirname(require.resolve("font-awesome/package.json")); // eslint-disable-line no-undef
  let faFontPath = path.resolve(fABasePath, "fonts", "*.*");

  return gulp.src(faFontPath)
              .pipe(gulp.dest(path.join(distPath, "fonts")));
});


gulp.task("dist:font-awesome",
  ["dist:font-awesome:css", "dist:font-awesome:fonts"]);


gulp.task("dist:images", () => {
  return gulp.src(path.join(staticPrefix, "images", "**", "*"))
              .pipe(gulpImage({
                "svgo": false,  // SVGO is currently broken.
              }))
              .pipe(gulp.dest(path.join(distPath, "images")));
});


gulp.task("dist:manifest", () => {
  let paths = [
    // Cachebust our CSS files and the source maps for them.
    path.join(distPath, "css", "*.css"),
    path.join(distPath, "css", "*.map"),

    // Cachebust our Font files.
    path.join(distPath, "fonts", "*"),

    // Cachebust our JS files and the source maps for them.
    path.join(distPath, "js", "*.js"),
    path.join(distPath, "js", "*.map"),

    // Cachebust our Image files.
    path.join(distPath, "images", "*"),
  ];

  return gulp.src(paths, { base: distPath })
              .pipe(manifest.revision({
                fileNameManifest: "manifest.json",
                includeFilesInManifest: [
                  ".css",
                  ".map",
                  ".woff",
                  ".woff2",
                  ".svg",
                  ".eot",
                  ".ttf",
                  ".otf",
                  ".png",
                  ".ico",
                  ".js",
                ],
              }))
              .pipe(gulp.dest(distPath))
              .pipe(manifestClean({ verbose: false }))
              .pipe(manifest.manifestFile())
              .pipe(gulp.dest(distPath));
});


gulp.task("dist:compress:gz", () => {
  return gulp.src(path.join(distPath, "**", "*"))
              .pipe(gzip({
                skipGrowingFiles: true,
                gzipOptions: { level: 9, memLevel: 9 },
              }))
              .pipe(gulp.dest(distPath));
});


gulp.task("dist:compress:br:generic", () => {
  let paths = [
    path.join(distPath, "fonts", "*.otf"),
    path.join(distPath, "fonts", "*.woff"),
    path.join(distPath, "fonts", "*.woff2"),
    path.join(distPath, "fonts", "*.ttf"),
    path.join(distPath, "fonts", "*.eot"),
    path.join(distPath, "fonts", "*.svg"),

    path.join(distPath, "images", "*.png"),
    path.join(distPath, "images", "*.svg"),
    path.join(distPath, "images", "*.ico"),
  ];

  return gulp.src(paths, { base: distPath })
              .pipe(brotli.compress({skipLarger: true, mode: 0, quality: 11}))
              .pipe(gulp.dest(distPath));
});


gulp.task("dist:compress:br:text", () => {
  let paths = [
    path.join(distPath, "css", "*.css"),
    path.join(distPath, "css", "*.map"),
    path.join(distPath, "js", "*.js"),
    path.join(distPath, "js", "*.map"),
    path.join(distPath, "manifest.json"),
  ];

  return gulp.src(paths, { base: distPath })
              .pipe(brotli.compress({skipLarger: true, mode: 1, quality: 11}))
              .pipe(gulp.dest(distPath));
});


gulp.task(
  "dist:compress:br",
  ["dist:compress:br:generic", "dist:compress:br:text"]
);


gulp.task("dist:compress", ["dist:compress:gz", "dist:compress:br"]);


gulp.task("dist", (cb) => {
  return gulpSequence(
    // Ensure that we have a good clean base to start out with, by blowing away
    // any previously built files.
    "clean",
    // Build all of our static assets.
    ["dist:font-awesome", "dist:css", "dist:js"],
    // We have this here, instead of in the list above even though there is no
    // ordering dependency so that all of it's output shows up together which
    // makes it easier to read.
    "dist:images",
    // This has to be on it's own, and it has to be one of the last things we do
    // because otherwise we won't catch all of the files in the revisioning
    // process.
    "dist:manifest",
    // Finally, once we've done everything else, we'll compress everything that
    // we've gotten.
    "dist:compress"
  )(cb);
});


gulp.task("clean", () => { return del(distPath); });


gulp.task("watch", ["dist"], () => {
  let watchPaths = [
    path.join(staticPrefix, "**", "*"),
    path.join("!" + distPath, "**", "*"),
  ];

  gulpWatch(
    watchPaths,
    gulpBatch((_, done) => { gulp.start("dist", done); })
  );
});


gulp.task("default", ["dist"]);
