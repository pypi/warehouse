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

const tooltipClasses = ["tooltipped", "tooltipped-s", "tooltipped-immediate"];
let passwordFormRoot = document;

const passwordStrengthValidator = () => {
  let passwordGauge = document.querySelector(".password-strength__gauge");
  let score = parseInt(passwordGauge.getAttribute("data-zxcvbn-score"));
  if (!isNaN(score) && score < 2) {
    return passwordGauge.querySelector(".sr-only").innerHTML;
  } else {
    return null;
  }
};

const fieldRequiredValidator = (value) => {
  return value === ""?
    "Please fill out this field" : null;
};

const attachTooltip = (field, message) => {
  let parentNode = field.parentNode;
  parentNode.classList.add.apply(parentNode.classList, tooltipClasses);
  parentNode.setAttribute("aria-label", message);
};

const removeTooltips = () => {
  let tooltippedNodes = passwordFormRoot.querySelectorAll(".tooltipped");
  for (let tooltippedNode of tooltippedNodes) {
    tooltippedNode.classList.remove.apply(tooltippedNode.classList, tooltipClasses);
    tooltippedNode.removeAttribute("aria-label");
  }
};

const validateForm = (event) => {
  removeTooltips();
  let inputFields = passwordFormRoot.querySelectorAll("input[required='required']");
  for (let inputField of inputFields) {
    let requiredMessage = fieldRequiredValidator(inputField.value);
    if (requiredMessage !== null) {
      attachTooltip(inputField, requiredMessage);
      event.preventDefault();
      return false;
    }
  }

  let password = passwordFormRoot.querySelector("#new_password");
  let passwordStrengthMessage = passwordStrengthValidator(password.value);
  if (passwordStrengthMessage !== null) {
    attachTooltip(password, passwordStrengthMessage);
    event.preventDefault();
    return false;
  }
};

export function registerFormValidation() {
  const newPasswordNode = document.querySelector("#new_password");
  if (newPasswordNode === null) return;
  passwordFormRoot = document.evaluate(
    "./ancestor::form", newPasswordNode, null,
    XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
  const submitButton = passwordFormRoot.querySelector("input[type='submit']");
  submitButton.addEventListener("click", validateForm, false);
}
