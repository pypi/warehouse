export default () => {
  const togglePanelDisplay = (display, event) => {
    event.preventDefault();
    var elements = document.querySelectorAll(".-js-dark-overlay, .-js-filter-panel");
    for (var el of elements) {
      el.style.display = display;
    }
  };

  const toggleEvent = (element, display) => {
    element.addEventListener("click", togglePanelDisplay.bind(null, display), false);
  };

  const toggleAccordion = (el) => {
    el.className = el.className === "accordion" ? "accordion accordion--closed" : "accordion";
  };

  var showPanel = document.querySelector(".-js-add-filter");
  var hidePanel = document.querySelector(".-js-close-panel");

  if (!showPanel) return;

  for (var trigger of document.querySelectorAll(".-js-accordion-trigger")) {
    trigger.addEventListener("click", toggleAccordion.bind(null, trigger.parentElement), false);
  }

  toggleEvent(showPanel, "block");
  toggleEvent(hidePanel, "none");
};