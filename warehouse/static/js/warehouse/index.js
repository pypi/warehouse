/* SPDX-License-Identifier: Apache-2.0 */

// Import stimulus
import { Application } from "@hotwired/stimulus";
import { definitionsFromContext } from "@hotwired/stimulus-webpack-helpers";
import { Autocomplete } from "stimulus-autocomplete";

// We'll use docReady as a modern replacement for $(document).ready() which
// does not require all of jQuery to use. This will let us use it without
// having to load all of jQuery, which will make things faster.
import docReady from "warehouse/utils/doc-ready";

// Import our utility functions
import HTMLInclude from "warehouse/utils/html-include";
import * as formUtils from "warehouse/utils/forms";
import PositionWarning from "warehouse/utils/position-warning";
import Statuspage from "warehouse/utils/statuspage";
import timeAgo from "warehouse/utils/timeago";
import searchFilterToggle from "warehouse/utils/search-filter-toggle";
import BindModalKeys from "warehouse/utils/bind-modal-keys";
import BindFilterKeys from "warehouse/utils/bind-filter-keys";
import {GuardWebAuthn, AuthenticateWebAuthn, ProvisionWebAuthn} from "warehouse/utils/webauthn";
import "warehouse/utils/proxy-protection";

// Show unsupported browser warning if necessary
docReady(() => {
  if (navigator.appVersion.includes("MSIE 10")) {
    if (document.getElementById("unsupported-browser") !== null) return;

    let warning_div = document.createElement("div");
    warning_div.innerHTML = "<div id='unsupported-browser' class='notification-bar notification-bar--warning' role='status'><span class='notification-bar__icon'><i class='fa fa-exclamation-triangle' aria-hidden='true'></i><span class='sr-only'>Warning:</span></span><span class='notification-bar__message'>You are using an unsupported browser, please upgrade to a newer version.</span></div>";

    document.getElementById("sticky-notifications").appendChild(warning_div);
  }
});

// Human-readable timestamps for project histories
docReady(() => {
  timeAgo();
});

// toggle search panel behavior
docReady(() => {
  if (document.querySelector(".-js-add-filter")) searchFilterToggle();
});

// Kick off the client side HTML includes.
docReady(HTMLInclude);

// Handle the JS based automatic form submission.
docReady(formUtils.submitTriggers);
docReady(formUtils.registerFormValidation);

docReady(Statuspage);

// Close modals when escape button is pressed
docReady(() => {
  document.addEventListener("keydown", event => {
    // Only handle the escape key press when a modal is open
    if (document.querySelector(".modal:target") && event.keyCode === 27) {
      for (let element of document.querySelectorAll(".modal")) {
        application
          .getControllerForElementAndIdentifier(element, "confirm")
          .cancel();
      }
    }
  });
});

// Position sticky bar
docReady(() => {
  setTimeout(PositionWarning, 200);
});

docReady(() => {
  let resizeTimer;
  const onResize = () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(PositionWarning, 200);
  };
  window.addEventListener("resize", onResize, false);
});

let bindDropdowns = function () {
  // Bind click handlers to dropdowns for keyboard users
  let dropdowns = document.querySelectorAll(".dropdown");
  for (let dropdown of dropdowns) {
    let trigger = dropdown.querySelector(".dropdown__trigger");
    let content = dropdown.querySelector(".dropdown__content");

    let openDropdown = function () {
      content.classList.add("display-block");
      content.removeAttribute("aria-hidden");
      trigger.setAttribute("aria-expanded", "true");
    };

    let closeDropdown = function () {
      content.classList.remove("display-block");
      content.setAttribute("aria-hidden", "true");
      trigger.setAttribute("aria-expanded", "false");
    };

    if (!trigger.dataset.dropdownBound) {
      // If the user has clicked the trigger (either with a mouse or by
      // pressing space/enter on the keyboard) show the content
      trigger.addEventListener("click", function () {
        if (content.classList.contains("display-block")) {
          closeDropdown();
        } else {
          openDropdown();
        }
      });

      // Close the dropdown when a user moves away with their mouse or keyboard
      let closeInactiveDropdown = function (event) {
        if (dropdown.contains(event.relatedTarget)) {
          return;
        }
        closeDropdown();
      };

      dropdown.addEventListener("focusout", closeInactiveDropdown, false);
      dropdown.addEventListener("mouseout", closeInactiveDropdown, false);

      // Close the dropdown if the user presses the escape key
      document.addEventListener("keydown", function(event) {
        if (event.key === "Escape") {
          closeDropdown();
        }
      });

      // Set the 'data-dropdownBound' attribute so we don't bind multiple
      // handlers to the same trigger after the client-side-includes load
      trigger.dataset.dropdownBound = true;
    }
  }
};

// Bind the dropdowns when the page is ready
docReady(bindDropdowns);

// Get modal keypress event listeners ready
docReady(BindModalKeys);

// Get filter pane keypress event listeners ready
docReady(BindFilterKeys);

// Get WebAuthn compatibility checks ready
docReady(GuardWebAuthn);

// Get WebAuthn provisioning ready
docReady(ProvisionWebAuthn);

// Get WebAuthn authentication ready
docReady(AuthenticateWebAuthn);

docReady(() => {
  const tokenSelect = document.getElementById("token_scope");

  if (tokenSelect === null) {
    return;
  }

  tokenSelect.addEventListener("change", () => {
    const tokenScopeWarning = document.getElementById("api-token-scope-warning");
    if (tokenScopeWarning === null) {
      return;
    }

    const tokenScope = tokenSelect.options[tokenSelect.selectedIndex].value;
    tokenScopeWarning.hidden = (tokenScope !== "scope:user");
  });
});

// Bind again when client-side includes have been loaded (for the logged-in
// user dropdown)
document.addEventListener("CSILoaded", bindDropdowns);
document.addEventListener("CSILoaded", PositionWarning);

const application = Application.start();
const context = require.context("./controllers", true, /\.js$/);
application.load(definitionsFromContext(context));
application.register("autocomplete", Autocomplete);
