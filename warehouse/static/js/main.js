// Note: This file only exists temporarily. Once the rest of this code gets
//       ported to using the ES6 syntax and is part of the warehouse package
//       this will be removed. New code should go in
//       warehouse/static/js/warehouse and not here.

import $ from "jquery";


$(document).ready(function() {

  // Toggle accordion
  $(".-js-accordion-trigger").click(function(){
    $(this).closest(".accordion").toggleClass("accordion--closed");
  });

  // Launch filter popover on mobile
  $("body").on("click", ".-js-add-filter", function(e){
    e.preventDefault();
    $(".-js-dark-overlay").show();
    $(".-js-filter-panel").show();
  });

  $("body").on("click", ".-js-close-panel", function(e){
    e.preventDefault();
    $(".-js-dark-overlay").hide();
    $(".-js-filter-panel").hide();
  });
});
