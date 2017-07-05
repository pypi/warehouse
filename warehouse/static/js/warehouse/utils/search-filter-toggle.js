/* Licensed under the Apache License, Version 2.0 (the "License");
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
