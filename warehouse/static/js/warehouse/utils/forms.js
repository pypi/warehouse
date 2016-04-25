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


let submitForm = (element) => {
  element.form.submit();
};


export function submitTriggers() {
  // Get all of the elements on the page with a -js-form-submit-trigger class
  // associated with them.
  let elements = Array.from(
      document.querySelectorAll(".-js-form-submit-trigger")
  );

  // Add an on change event handler to each element that will trigger the
  // containing for to submit whenever it is called.
  elements.forEach((element) => {
    element.addEventListener(
      "change",
      submitForm.bind(undefined, element),
      false
    );
  });
}
