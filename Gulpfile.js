var del = require("del"),
    gulp = require("gulp"),
    minifyCSS = require("gulp-minify-css"),
    path = require("path"),
    rename = require("gulp-rename"),
    rev = require("gulp-rev"),
    runSequence = require("run-sequence"),
    sass = require("gulp-sass"),
    sassLint = require("gulp-sass-lint");


var srcPaths = {
  sass: "warehouse/static/sass/",
  images: "warehouse/static/images/"
}

var dstPaths = {
  base: "warehouse/static/dist/",
  css: "warehouse/static/dist/css/",
  images: "warehouse/static/dist/images/"
}


gulp.task("lint:sass", function() {
  return gulp.src(path.join(srcPaths.sass, "**", "*.s+(a|c)ss"))
             .pipe(sassLint())
             .pipe(sassLint.format())
             .pipe(sassLint.failOnError())
});

gulp.task("lint", ["lint:sass"]);

gulp.task("dist:css", ["clean:css"], function() {
  return gulp.src(path.join(srcPaths.sass, "*.scss"))
             .pipe(sass({ includePaths: [srcPaths.sass] }))
             .pipe(minifyCSS({ keepBreaks: true }))
             .pipe(gulp.dest(dstPaths.css));
});

gulp.task("dist:images", ["clean:images"], function() {
  return gulp.src(path.join(srcPaths.images, "**", "*"))
             .pipe(gulp.dest(dstPaths.images));
})

gulp.task("dist:cachebuster", function() {
  var mpaths = [dstPaths.css, dstPaths.images].map(
    function (i){ return path.join(i, "**", "*") }
  );

  return gulp.src(mpaths, { base: path.join(__dirname, dstPaths.base) })
             .pipe(rev())
             .pipe(gulp.dest(dstPaths.base))
             .pipe(rev.manifest({ path: "manifest.json" }))
             .pipe(gulp.dest(dstPaths.base));
});

gulp.task("dist", function() {
    return runSequence(["dist:css", "dist:images"], "dist:cachebuster");
});

gulp.task("clean:css", function() { return del([dstPaths.css]) });

gulp.task("clean:images", function() { return del([dstPaths.images]) });

gulp.task("clean", ["clean:css", "clean:images"]);

gulp.task("watch", function() {
    gulp.watch(path.join(srcPaths.sass, "*.scss"), ["default"]);
});

gulp.task("default", ["dist"]);
