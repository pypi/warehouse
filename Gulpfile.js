var cssnano = require("gulp-cssnano"),
    del = require("del"),
    gulp = require("gulp"),
    gulpSequence = require("gulp-sequence"),
    imagemin = require("gulp-imagemin"),
    imageminOptipng = require("imagemin-optipng"),
    install = require("gulp-install"),
    mainBowerFiles = require("main-bower-files"),
    modernizr = require("gulp-modernizr"),
    path = require("path"),
    rename = require("gulp-rename"),
    revAll = require("gulp-rev-all"),
    sass = require("gulp-sass"),
    sassLint = require("gulp-sass-lint"),
    uglify = require("gulp-uglify"),
    sourcemaps = require('gulp-sourcemaps');


var srcPaths = {
  components: "warehouse/static/components",
  images: "warehouse/static/images/",
  js: "warehouse/static/js/",
  sass: "warehouse/static/sass/"
}


var dstPaths = {
  base: "warehouse/static/dist",
  components: "warehouse/static/dist/components",
  css: "warehouse/static/dist/css",
  images: "warehouse/static/dist/images",
  js: "warehouse/static/dist/js",
  maps: "warehouse/static/dist/maps"
}


gulp.task("lint:sass", function() {
  return gulp.src(path.join(srcPaths.sass, "**", "*.s+(a|c)ss"))
             .pipe(sassLint())
             .pipe(sassLint.format())
             .pipe(sassLint.failOnError())
});

gulp.task("lint", ["lint:sass"]);

gulp.task("dist:components:install", function() {
  return gulp.src(["bower.json"]).pipe(install({ allowRoot: true }));
})

gulp.task("dist:components:collect", function() {
  return gulp.src(mainBowerFiles(), { base: srcPaths.components })
             .pipe(gulp.dest(dstPaths.components));
});

gulp.task("dist:components:js", function() {
  return gulp.src(path.join(dstPaths.components, "**", "*.js"))
             .pipe(uglify({ preserveComments: "license" }))
             .pipe(gulp.dest(dstPaths.components));
});

gulp.task("dist:components:css", function() {
  return gulp.src(path.join(dstPaths.components, "**", "*.css"))
             .pipe(cssnano({ safe: true }))
             .pipe(gulp.dest(dstPaths.components));
});


gulp.task("dist:components", function(cb) {
  return gulpSequence(
    "dist:components:install",
    "dist:components:collect",
    ["dist:components:js", "dist:components:css"]
  )(cb);
});

gulp.task("dist:css", function() {
  return gulp.src(path.join(srcPaths.sass, "*.scss"))
             .pipe(sourcemaps.init())
             .pipe(sass({ includePaths: [srcPaths.sass] }))
             .pipe(cssnano({ safe: true }))
             .pipe(sourcemaps.write("../maps"))
             .pipe(gulp.dest(dstPaths.css));
});

gulp.task("dist:images", function() {
  return gulp.src(path.join(srcPaths.images, "**", "*"))
             .pipe(
               imagemin({
                 progressive: true,
                 interlaced: true,
                 multipass: true,
                 svgoPlugins: [{removeViewBox: false}],
                 use: [imageminOptipng()]
             }))
             .pipe(gulp.dest(dstPaths.images));
});

gulp.task("dist:js", function() {
  return gulp.src(path.join(srcPaths.js, "**", "*"))
             .pipe(sourcemaps.init())
             .pipe(uglify({ preserveComments: "license" }))
             .pipe(sourcemaps.write("../maps"))
             .pipe(gulp.dest(dstPaths.js));
});

gulp.task("dist:modernizr", function() {
  return gulp.src(path.join(dstPaths.js, "**", "*.js"))
             .pipe(modernizr({ options : ["setClasses"] }))
             .pipe(uglify({ preserveComments: "license" }))
             .pipe(gulp.dest(dstPaths.components));
});

gulp.task("dist:manifest", function() {
  var revision = new revAll({ fileNameManifest: "manifest.json" });

  return gulp.src(path.join(dstPaths.base, "**"))
             .pipe(revision.revision())
             .pipe(gulp.dest(dstPaths.base))
             .pipe(revision.manifestFile())
             .pipe(gulp.dest(dstPaths.base));
});

gulp.task("dist", function(cb) {
  return gulpSequence(
    "clean",
    ["dist:components", "dist:css", "dist:images", "dist:js"],
    "dist:modernizr",
    "dist:manifest"
  )(cb);
});

gulp.task("clean:components", function() {
  return del([dstPaths.components])
});

gulp.task("clean:css", function() { return del([dstPaths.css]) });

gulp.task("clean:images", function() { return del([dstPaths.images]) });

gulp.task("clean:js", function() { return del([dstPaths.js]) });

gulp.task("clean:manifest", function() {
  return del([path.join(dstPaths.base, "manifest.json")]);
});

gulp.task("clean", [
  "clean:components",
  "clean:css",
  "clean:images",
  "clean:js",
  "clean:manifest"
]);

gulp.task("watch", ["dist"], function() {
  var globs = [
    path.join(srcPaths.components, "**/*"),
    path.join(srcPaths.images, "**/*"),
    path.join(srcPaths.js, "**/*"),
    path.join(srcPaths.sass, "**/*")
  ];

  return gulp.watch(globs, ["dist"]);
});

gulp.task("default", ["dist"]);
