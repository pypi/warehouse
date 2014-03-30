module.exports = function(grunt) {

  grunt.initConfig({

    watch: {
      files: ["warehouse/static/source/**/*"],
      tasks: ["default"],
    },

    clean: ["warehouse/static/compiled"],

    compass: {
      warehouse: {
        options: {
          basePath: "warehouse/static/source/warehouse",
          cssDir: "css",
          relativeAssets: true,
          noLineComments: true,
          assetCacheBuster: false,
        }
      },
    },

    cssmin: {
      all: {
        files: [
          {
            expand: true,
            cwd: "warehouse/static/source/bootstrap/css",
            src: ["*.css", "!*.min.css"],
            dest: "warehouse/static/compiled/css/"
          },
          {
            expand: true,
            cwd: "warehouse/static/source/warehouse/css",
            src: ["*.css"],
            dest: "warehouse/static/compiled/css/",
          },
        ]
      }
    },

    uglify: {
      options: { preserveComments: "some" },
      all: {
        files: [
          {
            src: "warehouse/static/source/bootstrap/js/bootstrap.js",
            dest: "warehouse/static/compiled/js/bootstrap.js"
          },
          {
            src: "warehouse/static/source/jquery/js/jquery.js",
            dest: "warehouse/static/compiled/js/jquery.js"
          },
        ]
      }
    },

    copy: {
      fonts: {
        files: [
          {
            expand: true,
            cwd: "warehouse/static/source/bootstrap/fonts",
            src: ["**"],
            dest: "warehouse/static/compiled/fonts"
          }
        ]
      }
    },

    filerev: {
      all: {
        src: "warehouse/static/compiled/{css,fonts,js}/*.*",
      }
    },

    filerev_assets: {
      all: {
        options: {
          dest: "warehouse/static/compiled/assets.json",
          cwd: "warehouse/static/compiled/",
          prettyPrint: true
        }
      }
    },

    cssurlrev: {
      options: { assets: "warehouse/static/compiled/assets.json" },
      all: {
        src: ["warehouse/static/compiled/css/*.css"]
      },
    },

    compress: {
      all: {
        options: { mode: "gzip", level: 9 },
        expand: true,
        cwd: "warehouse/static/compiled",
        src: [
          "**/*", "!assets.json",
          "!*.jpg", "!*.jpeg", "!*.png", "!*.gif", "!*.zip", "!*.gz", "!*.tgz",
          "!*.bz2", "!*.tbz", "!*.swf", "!*.flv",
        ],
        dest: "warehouse/static/compiled",
      }
    },

  });

  grunt.loadNpmTasks("grunt-contrib-watch");
  grunt.loadNpmTasks("grunt-contrib-clean");
  grunt.loadNpmTasks("grunt-contrib-compass");
  grunt.loadNpmTasks("grunt-contrib-cssmin");
  grunt.loadNpmTasks("grunt-contrib-uglify");
  grunt.loadNpmTasks("grunt-contrib-copy");
  grunt.loadNpmTasks("grunt-filerev");
  grunt.loadNpmTasks("grunt-filerev-assets");
  grunt.loadNpmTasks("grunt-cssurlrev");
  grunt.loadNpmTasks("grunt-contrib-compress");

  grunt.registerTask("hash", ["filerev", "filerev_assets", "cssurlrev"]);
  grunt.registerTask(
    "default",
    ["clean", "compass", "cssmin", "uglify", "copy", "hash", "compress"]
  );

};
