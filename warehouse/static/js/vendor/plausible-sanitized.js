window.plausible = window.plausible || function() { (window.plausible.q = window.plausible.q || []).push(arguments); };
window.plausible.init = window.plausible.init || function(options) { window.plausible.o = options || {}; };
// Capture the supported translation rendered by Warehouse before the async tracker loads.
window.plausible.init({
  autoCapturePageviews: false,
  customProperties: { "displayed translation": document.documentElement.lang },
});

// Build sanitized URL without query parameters
var url = window.location.protocol + "//" + window.location.host + window.location.pathname;
window.plausible("pageview", { url: url });
