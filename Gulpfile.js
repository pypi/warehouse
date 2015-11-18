var del = require("del"),
    gulp = require("gulp"),
    minifyCSS = require("gulp-minify-css"),
    path = require("path"),
    rename = require("gulp-rename"),
    rev = require("gulp-rev"),
    runSequence = require("run-sequence"),
    sass = require("gulp-sass");


var paths = {
    base: "warehouse/static/",
    css: "warehouse/static/css/",
    sass: "warehouse/static/sass/"
};


gulp.task("dist:css:warehouse", ["clean"], function() {
    return gulp.src(path.join(paths.sass, "*.scss"))
        .pipe(sass({ includePaths: [paths.sass] }))
        .pipe(minifyCSS({ keepBreaks: true }))
        .pipe(gulp.dest(paths.css));
});

gulp.task("dist:css", ["dist:css:warehouse"]);

gulp.task("dist:cachebuster", function() {
    var mpaths = [paths.css].map(function (i){ return path.join(i, "**", "*") });

    return gulp.src(mpaths, { base: path.join(__dirname, paths.base) })
        .pipe(rev())
        .pipe(gulp.dest(paths.base))
        .pipe(rev.manifest({ path: "manifest.json" }))
        .pipe(gulp.dest(paths.base));
});

gulp.task("dist", function() {
    return runSequence("dist:css", "dist:cachebuster");
});

gulp.task("clean", function() { return del([paths.css]) });

gulp.task("watch", function() {
    gulp.watch(path.join(paths.sass, "*.scss"), ["default"]);
});

gulp.task("default", ["dist"]);
