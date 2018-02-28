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

const tooltipClasses = ["tooltipped", "tooltipped-s", "tooltipped-immediate"];

const passwordStrengthValidator = (value) => {
  const zxcvbnResult = zxcvbn(value);
  return zxcvbnResult.score < 2 ?
    zxcvbnResult.feedback.suggestions.join(" ") : null;
};

const fieldRequiredValidator = (value) => {
  return value === ""?
    "Please fill out this field" : null;
};

const checkPasswordStrength = (event) => {
  let result = document.querySelector(".password-strength__gauge");
  if (event.target.value === "") {
    result.setAttribute("class", "password-strength__gauge");
    // Feedback for screen readers
    result.querySelector(".sr-only").innerHTML = "Password field is empty";
  } else {
    // following recommendations on the zxcvbn JS docs
    // the zxcvbn function is available by loading `vendor/zxcvbn.js`
    // in the register page template only
    let zxcvbnResult = zxcvbn(event.target.value);
    result.setAttribute("class", `password-strength__gauge password-strength__gauge--${zxcvbnResult.score}`);

    // Feedback for screen readers
    result.querySelector(".sr-only").innerHTML = zxcvbnResult.feedback.suggestions.join(" ") || "Password is strong";
  }
};

const setupPasswordStrengthGauge = () => {
  let password = document.querySelector("#new_password");
  if (password === null) return;
  password.addEventListener(
    "input",
    checkPasswordStrength,
    false
  );
};

const attachTooltip = (field, message) => {
  let parentNode = field.parentNode;
  parentNode.classList.add.apply(parentNode.classList, tooltipClasses);
  parentNode.setAttribute("aria-label", message);
};

const removeTooltips = () => {
  let tooltippedNodes = document.querySelectorAll(".tooltipped");
  for (let tooltippedNode of tooltippedNodes) {
    tooltippedNode.classList.remove.apply(tooltippedNode.classList, tooltipClasses);
    tooltippedNode.removeAttribute("aria-label");
  }
};

const validateForm = (event) => {
  removeTooltips();
  let inputFields = document.querySelectorAll("input[required='required']");
  for (let inputField of inputFields) {
    let requiredMessage = fieldRequiredValidator(inputField.value);
    if (requiredMessage !== null) {
      attachTooltip(inputField, requiredMessage);
      event.preventDefault();
      return false;
    }
  }

  let password = document.querySelector("#new_password");
  let passwordConfirm = document.querySelector("#password_confirm");
  if (password.value !== passwordConfirm.value) {
    let message = "Passwords do not match";
    attachTooltip(password, message);
    event.preventDefault();
    return false;
  }

  let passwordStrengthMessage = passwordStrengthValidator(password.value);
  if (passwordStrengthMessage !== null) {
    attachTooltip(password, passwordStrengthMessage);
    event.preventDefault();
    return false;
  }
};

export function registerFormValidation() {
  if (document.querySelector("#password_confirm") === null) return;
  setupPasswordStrengthGauge();
  const submitButton = document.querySelector("#content input[type='submit']");
  submitButton.addEventListener("click", validateForm, false);
}
