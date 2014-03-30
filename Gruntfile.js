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
    }

  });

  grunt.loadNpmTasks("grunt-contrib-compass");

  grunt.registerTask("default", ["compass"]);

};
