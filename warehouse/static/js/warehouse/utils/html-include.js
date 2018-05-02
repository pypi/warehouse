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

const fetchOptions = {
  mode: "same-origin",
  credentials: "same-origin",
  cache: "default",
  redirect: "follow",
};

export default () => {
  // Each HTML include will generate a promise, which we'll later use to wait
  // on once all the promises have been resolved.
  let promises = [];

  // Fetch all of the elements with a data-html-include attribute and put them
  // into an array.
  let elements = Array.from(document.querySelectorAll("[data-html-include]"));

  // For each element we found, fetch whatever URL is pointed to by the
  // data-html-include attribute and replace it's content with that. This uses
  // the new fetch() API which returns a Promise.
  elements.forEach((element) => {
    let p = fetch(element.getAttribute("data-html-include"), fetchOptions)
      .then(response => {
        if (response.ok) { return response.text(); }
        else { return ""; }
      })
      .then(content => { element.innerHTML = content; });
    promises.push(p);
  });

  Promise.all(promises).then(() => {

    // Once all of our HTML includes have fired, then we'll go ahead and record
    // the fact that our HTML includes have happened. This allows us to
    // introspect the state of our includes inside of our Selenium tests.
    window._WarehouseHTMLIncluded = true;

    // Dispatch an event to any listeners that our CSI includes have loaded
    var event = new Event("CSILoaded");
    document.dispatchEvent(event);
  });
};
