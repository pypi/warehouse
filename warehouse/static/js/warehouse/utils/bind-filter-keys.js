/**
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
