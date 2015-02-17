var del = require("del"),
    gulp = require("gulp"),
    minifycss = require("gulp-minify-css"),
    neat = require("node-neat").includePaths,
    path = require("path"),
    normalize = path.join(require.resolve("normalize.css/package.json"), ".."),
    rename = require("gulp-rename"),
    rev = require("gulp-rev"),
    sass = require("gulp-sass");


var paths = {
    base: "warehouse/static/",
    css: "warehouse/static/css/",
    sass: "warehouse/static/sass/"
};


gulp.task("dist:css:normalize", function() {
    return gulp.src(path.join(normalize, "normalize.css"))
        .pipe(minifycss())
        .pipe(gulp.dest(paths.css));
})


gulp.task("dist:css:warehouse", function() {
    return gulp.src(path.join(paths.sass, "*.scss"))
        .pipe(sass({ includePaths: [paths.sass].concat(neat) }))
        .pipe(minifycss())
        .pipe(gulp.dest(paths.css));
});

gulp.task("dist:css", ["dist:css:normalize", "dist:css:warehouse"]);

gulp.task("dist:cachebuster", function() {
    var mpaths = [paths.css].map(function (i){ return path.join(i, "**", "*") });

    return gulp.src(mpaths, { base: path.join(__dirname, paths.base) })
        .pipe(rev())
        .pipe(gulp.dest(paths.base))
        .pipe(rev.manifest({ path: "manifest.json" }))
        .pipe(gulp.dest(paths.base));
});

gulp.task("dist", ["dist:css"], function() { gulp.start("dist:cachebuster") });

gulp.task("clean", function(cb) { del([paths.css], cb) });

gulp.task("watch", function() {
    gulp.watch(path.join(paths.sass, "*.scss"), ["default"]);
});

gulp.task("default", ["clean"], function() { gulp.start("dist") });
