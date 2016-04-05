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
  // Fetch all of the elements with a data-html-include attribute and put them
  // into an array.
  let elements = Array.from(document.querySelectorAll("[data-html-include]"));

  // For each element we found, fetch whatever URL is pointed to by the
  // data-html-include attribute and replace it's content with that. This uses
  // the new fetch() API which returns a Promise.
  elements.forEach((element) => {
    fetch(element.getAttribute("data-html-include")).then((response) => {
      return response.text();
    }).then((content) => {
      element.innerHTML = content;
    });
  });
};
