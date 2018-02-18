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
  const mobileBtn = document.querySelector(".-js-vertical-tab-mobile-heading");
  let inMobileState = false;
  if (mobileBtn) {
    const styleProps = getComputedStyle(mobileBtn, null);
    inMobileState = (styleProps.getPropertyValue("display") === "block");
  }
  const btnClassName = inMobileState ? ".-js-vertical-tab-mobile-heading" : ".-js-vertical-tab";
  const activeClass = "vertical-tabs__tab--is-active";
  const getBtnByHref = (id) => document.querySelector(`${btnClassName}[href="#${id}"]`);
  const toggleTab = (clickedBtn, event) => {
    if (event) {
      event.preventDefault();
      history.pushState(null, "", clickedBtn.getAttribute("href"));
    }
    let id = clickedBtn.getAttribute("href").replace("#", "");
    // toggle display setting for the content related to the button
    for (var elem of document.querySelectorAll(".-js-vertical-tab-content")) {
      var btn = getBtnByHref(elem.id);
      if (elem.id === id) {
        elem.style.display = "block";
        btn.classList.add(activeClass);
      } else {
        elem.style.display = "none";
        btn.classList.remove(activeClass);
      }
    }
  };

  for (var btn of document.querySelectorAll(btnClassName)) {
    btn.addEventListener("click", toggleTab.bind(null, btn), false);
  }

  var initialContentId = location.hash ? location.hash.replace("#", "") : "description";
  var initialBtn = getBtnByHref(initialContentId);
  toggleTab(initialBtn);

  // I'm not sure if this is needed?
  window.addEventListener("hashchange", () => {
    var btn = getBtnByHref(location.hash.replace("#", ""));
    toggleTab(btn);
  }, false);

};
