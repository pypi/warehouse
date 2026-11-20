/* SPDX-License-Identifier: Apache-2.0 */

export default () => {
  // Force tab key to cycle within the filter panel if the filter panel is active.
  const keys = [];
  document.addEventListener("keydown", event => {
    const filterPanel = document.querySelector(".filter-panel");
    keys[event.keyCode] = event.type === "keydown";

    if (filterPanel === null) {
      return;
    }

    // The panel is only "active" as an overlay on smaller viewports, where
    // search-filter-toggle.js opens it by setting an inline `display: block`.
    // On larger viewports it is a static sidebar, and its close button is not
    // rendered: trapping focus there leaves keyboard users unable to tab
    // past the classifiers to the search results.
    if (filterPanel.style.display !== "block") {
      return;
    }

    // `firstItem` assumes that the close button is the first tabbable element.
    const firstItem = filterPanel.querySelector(".filter-panel__close");

    const getLastItem = () => {
      const lastAccordion = filterPanel.querySelector(".accordion:last-child");
      if (lastAccordion.classList.contains("accordion--closed")) {
        return lastAccordion.querySelector(".accordion__link");
      }
      // Take the last input in document order. A `li:last-child` selector
      // also matches nested tree items, which can stop well short of the
      // actual last item.
      const inputs = lastAccordion.querySelectorAll("li > input");
      return inputs[inputs.length - 1];
    };

    if (keys[9]) {
      // Handle SHIFT+TAB
      if (keys[9] && keys[16]) {
        if (document.activeElement === firstItem) {
          getLastItem().focus();
          event.preventDefault();
        }
      } else if (keys[9]) {
        if (document.activeElement === getLastItem()) {
          firstItem.focus();
          event.preventDefault();
        }
      }
    }
    else if (keys[27]) {
      firstItem.click();
    }
  });

  document.addEventListener("keyup", event => {
    keys[event.keyCode] = event.type === "keydown";
  });
};
