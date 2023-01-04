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

// Import the AdminLTE version of Bootstrap JS (4.x) to avoid namespace
// conflicts with other bootstrap packages.
// Related: https://github.com/ColorlibHQ/AdminLTE/commit/4f1546acb25dc73b034cb15a598171f4c2b3d835
import "admin-lte/node_modules/bootstrap";
// Import AdminLTE JS
import "admin-lte/build/js/AdminLTE";

// We'll use docReady as a modern replacement for $(document).ready() which
// does not require all of jQuery to use. This will let us use it without
// having to load all of jQuery, which will make things faster.
import docReady from "warehouse/utils/doc-ready";

import Clipboard from "clipboard";

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

// Copy handler for copy tooltips, e.g.
//   - the pip command on package detail page
//   - the copy hash on package detail page
//   - the copy hash on release maintainers page
//
// Copied from https://github.com/pypi/warehouse/blob/3ebae1ffe8f9f258f80eb8bf048f0e1fcc2df2b4/warehouse/static/js/warehouse/index.js#LL76-L107C4
docReady(() => {
  let setCopiedTooltip = (e) => {
    e.trigger.setAttribute("data-tooltip-label", "Copied");
    e.trigger.setAttribute("role", "alert");
    e.clearSelection();
  };

  new Clipboard(".copy-tooltip").on("success", setCopiedTooltip);

  let setOriginalLabel = (element) => {
    element.setAttribute("data-tooltip-label", "Copy to clipboard");
    element.removeAttribute("role");
    element.blur();
  };

  let tooltippedElems = Array.from(document.querySelectorAll(".copy-tooltip"));

  tooltippedElems.forEach((element) => {
    element.addEventListener("focusout",
      setOriginalLabel.bind(undefined, element),
      false
    );
    element.addEventListener("mouseout",
      setOriginalLabel.bind(undefined, element),
      false
    );
  });
});
