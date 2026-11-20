window.plausible = window.plausible || function() { (window.plausible.q = window.plausible.q || []).push(arguments); };
window.plausible.init = window.plausible.init || function(options) { window.plausible.o = options || {}; };
// Capture the supported translation rendered by Warehouse before the async tracker loads.
window.plausible.init({
  customProperties: { "displayed translation": document.documentElement.lang },
});
