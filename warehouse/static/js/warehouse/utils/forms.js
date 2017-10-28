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

const removeFilter = (value, event) => {
  event.preventDefault();
  const element = document.querySelector(`#classifiers input[value="${value}"]`);
  if (element) {
    element.checked = false;
    submitForm(element);
  }
};


export function submitTriggers() {
  // Get all of the elements on the page with a -js-form-submit-trigger class
  // associated with them.
  let elements = document.querySelectorAll(".-js-form-submit-trigger");

  // Add an on change event handler to each element that will trigger the
  // containing for to submit whenever it is called.

  for (const element of elements) {
    element.addEventListener("change", submitForm.bind(null, element), false);
  }

  const filters = document.querySelectorAll(".filter-badge");

  for (const filter of filters) {
    const [input, button] = [filter.firstElementChild, filter.lastElementChild];

    button.addEventListener(
      "click",
      removeFilter.bind(null, input.value),
      false
    );
  }
}

/* global zxcvbn */

const checkPasswordStrength = (event) => {
  let result = document.querySelector(".pw-strength-guage");
  if (event.target.value === "") {
    result.setAttribute("class", "pw-strength-guage");
  } else {
    // following recommendations on the zxcvbn JS docs
    // the zxcvbn function is available by loading `vendor/zxcvbn.js`
    // in the register page template only
    let zxcvbnResult = zxcvbn(event.target.value);
    result.setAttribute("class", `pw-strength-guage pw-strength-guage__${zxcvbnResult.score}`);
  }
};

export function passwordStrength() {
  let password = document.querySelector("#password");
  if (password === null) return;
  password.addEventListener("input", checkPasswordStrength, false);
}
