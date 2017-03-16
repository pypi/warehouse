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
    var element = event.currentTarget.parentElement;
    element.classList.toggle("accordion--closed");
  };

  for (var trigger of document.querySelectorAll(".-js-accordion-trigger")) {
    trigger.addEventListener("click", toggleAccordion, false);
  }

  toggleEvent(showPanel, "block");
  toggleEvent(hidePanel, "");
};