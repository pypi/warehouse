export default () => {
  var showPanel = document.querySelector(".-js-add-filter");
  var hidePanel = document.querySelector(".-js-close-panel");

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

  const toggleAccordion = (event) => {
    var el = event.currentTarget.parentElement;
    el.className = el.className === "accordion" ? "accordion accordion--closed" : "accordion";
  };

  for (var trigger of document.querySelectorAll(".-js-accordion-trigger")) {
    trigger.addEventListener("click", toggleAccordion, false);
  }

  toggleEvent(showPanel, "block");
  toggleEvent(hidePanel, "none");
};