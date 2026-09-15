window.plausible = window.plausible || function() { (window.plausible.q = window.plausible.q || []).push(arguments); };
window.plausible.init = window.plausible.init || function(options) { window.plausible.o = options || {}; };
window.plausible.init({ autoCapturePageviews: false });

// Build sanitized URL without query parameters
var url = window.location.protocol + "//" + window.location.host + window.location.pathname;
window.plausible("pageview", { url: url });
