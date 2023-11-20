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

import "admin-lte/plugins/jquery/jquery";
import "admin-lte/plugins/bootstrap/js/bootstrap.bundle";

// Import DataTables JS
import "admin-lte/plugins/datatables/jquery.dataTables";
import "admin-lte/plugins/datatables-bs4/js/dataTables.bootstrap4";
import "admin-lte/plugins/datatables-responsive/js/dataTables.responsive";
import "admin-lte/plugins/datatables-responsive/js/responsive.bootstrap4";
import "admin-lte/plugins/datatables-buttons/js/dataTables.buttons";
import "admin-lte/plugins/datatables-buttons/js/buttons.bootstrap4";
import "admin-lte/plugins/datatables-buttons/js/buttons.html5";
import "admin-lte/plugins/datatables-buttons/js/buttons.colVis";

// Import AdminLTE JS
import "admin-lte/build/js/AdminLTE";


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

// Copy handler for copying text, e.g.
//   - prohibited project names confirmation page
//
document.querySelectorAll(".copy-text").forEach(function (element) {
  function copy(text, target) {
    setTimeout(function () {
      $("#copied_tip").remove();
    }, 1000);
    $(target).append("<div class='tip' id='copied_tip'>Copied!</div>");
    navigator.clipboard.writeText(text);
  }

  element.addEventListener("click", function(event) {
    event.preventDefault();
    copy(element.dataset.copyText, element);
  });
});

// Activate Datatables https://datatables.net/
// User Account Activity
let table = $("#account-activity").DataTable({
  responsive: true,
  lengthChange: false,
});
// sort by time
table.column(".time").order("desc").draw();
// Hide some columns we don't need to see all the time
table.columns([".ip_address", ".hashed_ip"]).visible(false);
// add column visibility button
new $.fn.dataTable.Buttons(table, {buttons: ["copy", "csv", "colvis"]});
table.buttons().container().appendTo($(".col-md-6:eq(0)", table.table().container()));

// Observations
let obs_table = $("#observations").DataTable({
  responsive: true,
  lengthChange: false,
});
obs_table.column(".time").order("desc").draw();
obs_table.columns([".payload"]).visible(false);
new $.fn.dataTable.Buttons(obs_table, {buttons: ["copy", "csv", "colvis"]});
obs_table.buttons().container().appendTo($(".col-md-6:eq(0)", obs_table.table().container()));
