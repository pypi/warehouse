import $ from "jquery";
import "timeago";


export function renderCaptcha() {
  var config = { sitekey: $("script#recaptcha-js").data("site-key") };
  grecaptcha.render($("#recaptcha-container")[0], config);
}


$(document).ready(function() {

  // Toggle expanding and collapsing sections
  $(".-js-expander-trigger").click(function(){
    $(this).toggleClass("expander-hidden");
  });

  function setTab(tab) {
    if (tab) {
      $(".js-vertical-tab-content").hide();
      tab.show();
      $(".is-active").removeClass("is-active");
      $("a[href^='#"+tab[0].id+"']").addClass("is-active");
    }
  }

  function getTab(selector) {
    var tab = $(".js-vertical-tab-content" + selector);
    return (selector && tab.length) ? tab : null;
  }

  window.onhashchange = function() {
    setTab(getTab(location.hash) || getTab(":first"));
  };

  // Set the tab if the hash is valid, otherwise show the first tab
  setTab(getTab(location.hash) || getTab(":first"));

  // If in tab mode
  $(".-js-vertical-tab").click(function(event) {
    event.preventDefault();
    history.pushState(null, "", $(this).attr("href"));
    setTab(getTab(location.hash));
  });

  // If in accordion mode
  $(".-js-vertical-tab-accordion-heading").click(function(event) {
    event.preventDefault();
    history.pushState(null, "", $(this).attr("href"));
    setTab(getTab(location.hash));
  });

  // Launch filter popover on mobile
  $("body").on("click", ".-js-add-filter", function(e){
    e.preventDefault();
    $(".dark-overlay").show();
    $(".panel-overlay").show();
  });

  $("body").on("click", ".-js-close-panel", function(e){
    e.preventDefault();
    $(".dark-overlay").hide();
    $(".panel-overlay").hide();
  });

  // Position Sticky bar
  function positionWarning(){
    var height = $(".sticky-bar").outerHeight();
    $("body:has(.sticky-bar)").css("paddingTop", height);
  }

  positionWarning();

  $(window).resize(function(){
    positionWarning();
  });

  // Search ordering
  $("#order").on("change", function() {
    this.form.submit();
  });

  $.timeago.settings.cutoff = 7 * 24 * 60 * 60 * 1000;  // One week

  // document.l10n.ready.then(function() {
  //   // Format all of the time.relative tags to display relative time.
  //   $(".-js-relative-time").timeago();
  // });
  $(".-js-relative-time").timeago();  // Add back to document.l10n.ready

});
