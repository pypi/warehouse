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

    // `firstItem` assumes that the close button is the first tabbable element.
    const firstItem = filterPanel.querySelector(".filter-panel__close");

    const getLastItem = () => filterPanel.querySelector(
      ".accordion:last-child").classList.contains("accordion--closed")
      ? filterPanel.querySelector(".accordion:last-child > .accordion__link")
      : filterPanel.querySelector(".accordion:last-child li:last-child > input");

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
