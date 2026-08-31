/* SPDX-License-Identifier: Apache-2.0 */

// Import stimulus
import { Application } from "@hotwired/stimulus";
import { definitionsFromContext } from "@hotwired/stimulus-webpack-helpers";
import { Autocomplete } from "stimulus-autocomplete";

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

// Show unsupported browser warning if necessary
if (navigator.appVersion.includes("MSIE 10")) {
  if (document.getElementById("unsupported-browser") === null) {
    let warning_div = document.createElement("div");
    warning_div.innerHTML = "<div id='unsupported-browser' class='notification-bar notification-bar--warning' role='status'><span class='notification-bar__icon'><i class='fa fa-exclamation-triangle' aria-hidden='true'></i><span class='sr-only'>Warning:</span></span><span class='notification-bar__message'>You are using an unsupported browser, please upgrade to a newer version.</span></div>";

    document.getElementById("sticky-notifications").appendChild(warning_div);
  }
}

// Human-readable timestamps for project histories
timeAgo();

// toggle search panel behavior
if (document.querySelector(".-js-add-filter")) searchFilterToggle();

// Kick off the client side HTML includes.
HTMLInclude();

// Handle the JS based automatic form submission.
formUtils.submitTriggers();
formUtils.registerFormValidation();

Statuspage();

// Close modals when escape button is pressed
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

// Position sticky bar
setTimeout(PositionWarning, 200);

let resizeTimer;
const onResize = () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(PositionWarning, 200);
};
window.addEventListener("resize", onResize, false);

// Get modal keypress event listeners ready
BindModalKeys();

// Get filter pane keypress event listeners ready
BindFilterKeys();

// Get WebAuthn compatibility checks ready
GuardWebAuthn();

// Get WebAuthn provisioning ready
ProvisionWebAuthn();

// Get WebAuthn authentication ready
AuthenticateWebAuthn();

const tokenSelect = document.getElementById("token_scope");

if (tokenSelect !== null) {
  tokenSelect.addEventListener("change", () => {
    const tokenScopeWarning = document.getElementById("api-token-scope-warning");
    if (tokenScopeWarning === null) {
      return;
    }

    const tokenScope = tokenSelect.options[tokenSelect.selectedIndex].value;
    tokenScopeWarning.hidden = (tokenScope !== "scope:user");
  });
}

document.addEventListener("CSILoaded", PositionWarning);

const application = Application.start();
const context = require.context("./controllers", true, /\.js$/);
application.load(definitionsFromContext(context));
application.register("autocomplete", Autocomplete);
