/* SPDX-License-Identifier: Apache-2.0 */

export default () => {
  var showPanel = document.querySelector(".-js-add-filter");
  var hidePanel = document.querySelector(".-js-close-panel");
  var firstFilter = document.querySelector("#classifiers > .accordion > button");

  const togglePanelDisplay = (display, focusOn, event) => {
    event.preventDefault();
    var elements = document.querySelectorAll(".-js-dark-overlay, .-js-filter-panel");
    for (var el of elements) {
      el.style.display = display;
    }
    focusOn.focus();
  };

  const toggleEvent = (element, display, focusOn) => {
    element.addEventListener("click", togglePanelDisplay.bind(null, display, focusOn), false);
  };

  const toggleAccordion = (event) => {
    var trigger = event.currentTarget;
    if (trigger.getAttribute("aria-expanded") === "true") {
      trigger.setAttribute("aria-expanded", "false");
    } else {
      trigger.setAttribute("aria-expanded", "true");
    }

    var accordion = trigger.parentElement;
    accordion.classList.toggle("accordion--closed");

    var accordionContent = trigger.nextElementSibling;
    if (accordionContent.getAttribute("aria-hidden") === "true") {
      accordionContent.setAttribute("aria-hidden", "false");
    } else {
      accordionContent.setAttribute("aria-hidden", "true");
    }
  };

  for (var trigger of document.querySelectorAll(".-js-accordion-trigger")) {
    trigger.addEventListener("click", toggleAccordion, false);
  }

  toggleEvent(showPanel, "block", firstFilter);
  toggleEvent(hidePanel, "", showPanel);
};
