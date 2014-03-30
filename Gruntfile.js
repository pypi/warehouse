module.exports = function(grunt) {

  grunt.initConfig({

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
      bootstrap: {
        expand: true,
        cwd: "warehouse/static/source/bootstrap/css",
        src: ["*.css", "!*.min.css"],
        dest: "warehouse/static/compiled/css/",
      },
      warehouse: {
        expand: true,
        cwd: "warehouse/static/source/warehouse/css",
        src: ["*.css"],
        dest: "warehouse/static/compiled/css/",
      }
    },

    uglify: {
      bootstrap: {
        options: {
          preserveComments: "some",
        },
        files: {
          "warehouse/static/compiled/js/bootstrap.js" : [
            "warehouse/static/source/bootstrap/js/bootstrap.js",
          ]
        }
      }
    },

    filerev: {
      all: {
        src: "warehouse/static/compiled/{js,css}/*.*",
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
    }

  });

  grunt.loadNpmTasks("grunt-contrib-clean");
  grunt.loadNpmTasks("grunt-contrib-compass");
  grunt.loadNpmTasks("grunt-contrib-cssmin");
  grunt.loadNpmTasks("grunt-contrib-uglify");
  grunt.loadNpmTasks("grunt-filerev");
  grunt.loadNpmTasks("grunt-filerev-assets");

  grunt.registerTask("hash", ["filerev", "filerev_assets"]);
  grunt.registerTask("default", ["clean", "compass", "cssmin", "uglify", "hash"]);

};
