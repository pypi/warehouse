window.plausible = window.plausible || function() { (window.plausible.q = window.plausible.q || []).push(arguments); };

// Build sanitized URL without query parameters
var url = window.location.protocol + "//" + window.location.host + window.location.pathname;
window.plausible("pageview", { u: url });
