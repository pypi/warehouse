$(document).ready(function() {

  // Toggle expanding and collapsing sections
  $('.expander-trigger').click(function(){
    $(this).toggleClass("expander-hidden");
  });

  $(".js-vertical-tab-content").hide();
  $(".js-vertical-tab-content:first").show();

  /* if in tab mode */
  $(".js-vertical-tab").click(function(event) {
    event.preventDefault();

    $(".js-vertical-tab-content").hide();
    var activeTab = $(this).attr("rel");
    $("#"+activeTab).show();

    $(".js-vertical-tab").removeClass("is-active");
    $(this).addClass("is-active");

    $(".js-vertical-tab-accordion-heading").removeClass("is-active");
    $(".js-vertical-tab-accordion-heading[rel^='"+activeTab+"']").addClass("is-active");
  });

  /* if in accordion mode */
  $(".js-vertical-tab-accordion-heading").click(function(event) {
    event.preventDefault();

    $(".js-vertical-tab-content").hide();
    var accordion_activeTab = $(this).attr("rel");
    $("#"+accordion_activeTab).show();

    $(".js-vertical-tab-accordion-heading").removeClass("is-active");
    $(this).addClass("is-active");

    $(".js-vertical-tab").removeClass("is-active");
    $(".js-vertical-tab[rel^='"+accordion_activeTab+"']").addClass("is-active");
  });

  // Launch filter popover on mobile
  $('body').on('click', '.add-filter', function(e){
    e.preventDefault();
    $('.dark-overlay').show();
    $('.panel-overlay').show();
  });

  $('body').on('click', '.close-panel', function(e){
    e.preventDefault();
    $('.dark-overlay').hide();
    $('.panel-overlay').hide();
  });

  // Position Sticky bar
  function positionWarning(){
    var height = $('.sticky-bar').outerHeight();
    $('body:has(.sticky-bar)').css('paddingTop', height);
  }

  positionWarning();

  $(window).resize(function(){
    positionWarning();
  });

});
