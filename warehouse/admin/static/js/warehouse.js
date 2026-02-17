/* SPDX-License-Identifier: Apache-2.0 */

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
import "admin-lte/plugins/datatables-rowgroup/js/dataTables.rowGroup";
import "admin-lte/plugins/datatables-rowgroup/js/rowGroup.bootstrap4";

// Import Chart JS
import "admin-lte/plugins/chart.js/Chart";

// Import AdminLTE JS
import "admin-lte/build/js/AdminLTE";

import "./treeview";
import "./observer_charts";

// Get our timeago function
import timeAgo from "warehouse/utils/timeago";

// Human-readable timestamps
$(document).ready(function() {
  timeAgo();
});

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
//   - user account recoveries
//
document.querySelectorAll(".copy-text").forEach(function (element) {
  $(element).tooltip({ title: "Click to copy!" });
  function copy(text) {
    setTimeout(function () {
      $(element).tooltip("hide")
        .attr("data-original-title", "Click to copy!");
    }, 1000);
    $(element).tooltip("hide")
      .attr("data-original-title", "Copied!")
      .tooltip("show");
    navigator.clipboard.writeText(text);
  }

  element.addEventListener("click", function(event) {
    event.preventDefault();
    copy(element.dataset.copyText, element);
  });
});

// Activate Datatables https://datatables.net/
// Guard each one to not break execution if the table isn't present

// User Account Activity
let accountActivityTable = $("#account-activity");
if (accountActivityTable.length) {
  let table = accountActivityTable.DataTable({
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
}

// User API Tokens
let tokenTable = $("#api-tokens");
if (tokenTable.length) {
  let table = tokenTable.DataTable({
    responsive: true,
    lengthChange: false,
  });
  table.columns([".last_used", ".created"]).order([1, "desc"]).draw();
  table.columns([".permissions_caveat"]).visible(false);
  new $.fn.dataTable.Buttons(table, {buttons: ["colvis"]});
  table.buttons().container().appendTo($(".col-md-6:eq(0)", table.table().container()));
}

// Observations
// Note: Each of these tables **must** have the same columns for this to work.
const tableSelectors = ["#observations", "#user_observations"];

tableSelectors.forEach(selector => {
  let tableElement = $(selector);
  if (tableElement.length) {
    let table = tableElement.DataTable({
      responsive: true,
      lengthChange: false,
    });
    table.column(".time").order("desc").draw();
    table.columns([".payload"]).visible(false);
    new $.fn.dataTable.Buttons(table, {buttons: ["copy", "csv", "colvis"]});
    table.buttons().container().appendTo($(".col-md-6:eq(0)", table.table().container()));
  }
});

// Malware Reports
let malwareReportsTable = $("#malware-reports");
if (malwareReportsTable.length) {
  let table = malwareReportsTable.DataTable({
    displayLength: 25,
    lengthChange: false,
    order: [[1, "desc"], [0, "asc"], [3, "desc"]],  // report count, alpha name, recent date
    responsive: true,
    rowGroup: {
      dataSrc: 0,
      // display row count in group header
      startRender: function (rows, group) {
        return group + " (" + rows.count() + ")";
      },
    },
  });
  // hide the project name and count, since they're in the group title
  table.columns([0, 1]).visible(false);
  new $.fn.dataTable.Buttons(table, {buttons: ["copy", "csv", "colvis"]});
  table.buttons().container().appendTo($(".col-md-6:eq(0)", table.table().container()));
}

// Organization Applications
let OrganizationApplicationsTable = $("#organization-applications");
if (OrganizationApplicationsTable.length) {
  let table = OrganizationApplicationsTable.DataTable({
    displayLength: 25,
    lengthChange: true,
    order: [[4, "asc"], [0, "asc"]],  // created, alpha name
    responsive: true,
  });
  new $.fn.dataTable.Buttons(table, {buttons: ["copy", "csv", "colvis"]});
  table.buttons().container().appendTo($(".col-md-6:eq(0)", table.table().container()));
}

let organizationApplicationTurboModeSwitch = document.getElementById("organizationApplicationTurboMode");
if (organizationApplicationTurboModeSwitch !== null) {
  let organizationApplicationTurboModeEnabled = JSON.parse(localStorage.getItem("organizationApplicationTurboModeEnabled") || false);
  organizationApplicationTurboModeSwitch.addEventListener("click", (event) => {
    localStorage.setItem("organizationApplicationTurboModeEnabled", event.target.checked);
    document.querySelectorAll("input[name=organization_applications_turbo_mode]").forEach(function(input) {
      input.value = event.target.checked;
    });
  });
  organizationApplicationTurboModeSwitch.checked = organizationApplicationTurboModeEnabled;
  document.querySelectorAll("input[name=organization_applications_turbo_mode]").forEach(function(input) {
    input.value = organizationApplicationTurboModeEnabled;
  });
  if (organizationApplicationTurboModeEnabled) {
    [...document.querySelectorAll(".alert-dismissible")].forEach(function(alertElem) {
      setTimeout(function() {alertElem.getElementsByTagName("button")[0].click();}, 1000);
    });
  }
}

const savedReplyButtons = document.querySelectorAll(".saved-reply-button");

if (savedReplyButtons.length > 0) {
  const requestMoreInfoModalMessage = document.getElementById("requestMoreInfoModalMessage");

  if (requestMoreInfoModalMessage) {
    savedReplyButtons.forEach(button => {
      button.addEventListener("click", () => {
        const templateId = button.dataset.template;

        if (templateId) {
          const templateElement = document.getElementById(templateId);

          if (templateElement) {
            const templateContent = templateElement.innerHTML;
            const cleanedContent = templateContent
              .trim()
              .replace(/\n/g, " ")
              .replace(/\s{2,}/g, " ");
            requestMoreInfoModalMessage.value = cleanedContent;
          }
        }
      });
    });
  }
}

let editModalForm = document.getElementById("editModalForm");
if (editModalForm !== null) {
  if (editModalForm.classList.contains("edit-form-errors")) {
    document.getElementById("editModalButton").click();
  }
}

$(document).ready(function() {
  const modalHotKeyBindings = document.querySelectorAll("button[data-hotkey-binding]");
  var keyBindings = new Map();
  function bindHotKeys() {
    document.onkeyup = hotKeys;
  }
  function unbindHotKeys() {
    document.onkeyup = function(){};
  }
  function hotKeys(e) {
    if (keyBindings.has(String(e.which))) {
      unbindHotKeys();
      const targetModal = $(keyBindings.get(String(e.which)));
      targetModal.one("shown.bs.modal", function () {
        const firstFocusableElement = $(this).find("input:visible, textarea:visible").first();
        if (firstFocusableElement.length) {
          firstFocusableElement.focus();
        }
      });
      targetModal.modal("show");
      targetModal.on("hidden.bs.modal", bindHotKeys);
    }
  }
  modalHotKeyBindings.forEach(function(modalHotKeyBinding) {
    if (! modalHotKeyBinding.disabled) {
      keyBindings.set(modalHotKeyBinding.dataset.hotkeyBinding, modalHotKeyBinding.dataset.target);
    }
  });
  const focusable = document.querySelectorAll("input, textarea");
  focusable.forEach(function(element) {
    element.addEventListener("focusin", unbindHotKeys);
    element.addEventListener("focusout", bindHotKeys);
  });
  bindHotKeys();
});

// Link Checking
const links = document.querySelectorAll("a[data-check-link-url]");
links.forEach(function(link){
  let reportLine = {bareUrl: link.href, url: link.dataset.checkLinkUrl, status:0, element : link};
  fetch(reportLine.url, {
    method: "GET",
    mode: "cors",
  })
    .then(function(response) {
      let responseText = "";
      response.text().then((text) => {
        responseText = text;
        if (response.status === 400 && responseText === "Unsupported content-type returned\n") {
          reportLine.element.firstChild.classList.remove("fa-question");
          reportLine.element.firstChild.classList.add("fa-check");
          reportLine.element.firstChild.classList.add("text-green");
          reportLine.status = 1;
        } else {
          reportLine.status = 0;
          reportLine.element.firstChild.classList.remove("fa-question");
          reportLine.element.firstChild.classList.add("fa-times");
          reportLine.element.firstChild.classList.add("text-red");
        }
      });
    })
    .catch(() => {
      reportLine.status = -1;
      reportLine.element.firstChild.classList.remove("fa-question");
      reportLine.element.firstChild.classList.add("fa-times");
      reportLine.element.firstChild.classList.add("text-red");
    });
});
