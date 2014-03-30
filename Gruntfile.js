module.exports = function(grunt) {

  grunt.initConfig({

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
    }

  });

  grunt.loadNpmTasks("grunt-contrib-compass");
  grunt.loadNpmTasks("grunt-contrib-uglify");

  grunt.registerTask("default", ["compass", "uglify"]);

};
