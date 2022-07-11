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

document.querySelectorAll("a[data-form-submit]").forEach(function (element) {
  element.addEventListener("click", function(event) {
    // We're turning this element into a form submission, so instead of the
    // default action, this event will handle things.
    event.preventDefault();

    // Find the form identified by our formSubmit, and submit it.
    document.querySelector("form#" + element.dataset.formSubmit).submit();
  });
});

document.querySelectorAll("a[data-input][data-append]").forEach(function (element) {
  element.addEventListener("click", function(event) {
    // We're turning this element into an input edit, so instead of the
    // default action, this event will handle things.
    event.preventDefault();

    // Find the input identified by data-input, and append string.
    const input = document.querySelector("input#" + element.dataset.input);
    if (!input.value) {
      input.value = element.dataset.append;
    } else if (input.value.endsWith(" ")) {
      input.value = input.value + element.dataset.append;
    } else {
      input.value = input.value + " " + element.dataset.append;
    }

    // Set cursor at end of input.
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  });
});

document.querySelectorAll(".btn-group[data-input][data-state]").forEach(function (btnGroup) {
  // Get options within the button group.
  const btns = btnGroup.querySelectorAll(".btn[data-" + btnGroup.dataset.state + "]");
  const options = Array.prototype.map.call(btns, btn => btn.dataset[btnGroup.dataset.state]);

  // Toggle options with each button click.
  btns.forEach(function (btn) {
    btn.addEventListener("click", function (event) {
      // We're turning this button into an input edit, so instead of the
      // default action, this event will handle things.
      event.preventDefault();

      // Find the input identified by data-input, and toggle option.
      const input = document.querySelector("input#" + btnGroup.dataset.input);
      const option = btn.dataset[btnGroup.dataset.state];
      let tokens = input.value.length ? input.value.split(" ") : [];
      if (btn.classList.contains("active")) {
        tokens = tokens.filter(token => token !== option);
      } else {
        tokens = tokens.map(token => options.includes(token) ? option : token);
        tokens = tokens.filter((token, i) => token !== option || i === tokens.indexOf(option));
        if (!tokens.includes(option)) tokens.push(option);
      }
      input.value = tokens.join(" ");

      // Find the form for the input, and submit it.
      input.form.submit();
    });
  });
});
