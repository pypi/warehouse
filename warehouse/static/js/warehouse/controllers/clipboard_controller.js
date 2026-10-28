/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";
import { gettext } from "../utils/messages-access";

// Copy handler for copy tooltips, e.g.
//   - the pip command on package detail page
//   - the copy hash on package detail page
//   - the copy hash on release maintainers page

// See `warehouse/static/sass/blocks/_copy-tooltip.scss` for style details.

const STATUS_ID = "clipboard-status";
// Shared by all controllers, as they share the one status region
let statusTimeout;

export default class extends Controller {
  static targets = [ "source", "tooltip" ];
  static values = {
    plausibleEvent: String,
  };

  connect() {
    // A live region must be in the page before its text changes for screen
    // readers to announce it, so create one shared region up front.
    // It lives on <body> as some controllers are on elements (e.g. <tr>)
    // that can't hold one.
    if (!document.getElementById(STATUS_ID)) {
      const status = document.createElement("div");
      status.id = STATUS_ID;
      status.className = "sr-only";
      status.setAttribute("role", "status");
      document.body.append(status);
    }
  }

  async copy() {
    if (this.hasPlausibleEventValue && window.plausible) {
      window.plausible(this.plausibleEventValue);
    }

    // copy the source text to clipboard
    try {
      await navigator.clipboard.writeText(this.sourceTarget.textContent);
    } catch {
      // the browser refused (e.g. permission denied), so don't claim it worked
      return;
    }

    const copiedMessage = gettext("Copied");
    // save the original tooltip text
    const clipboardTooltipOriginalValue = this.tooltipTarget.dataset.clipboardTooltipValue;
    // set the tooltip text
    this.tooltipTarget.dataset.clipboardTooltipValue = copiedMessage;
    // announce the copy to screen readers
    this._announce(copiedMessage);

    // on focusout and mouseout, reset the tooltip text to the original value
    const resetTooltip = () => {
      // restore the original tooltip text
      this.tooltipTarget.dataset.clipboardTooltipValue = clipboardTooltipOriginalValue;
      // remove focus
      this.tooltipTarget.blur();
      // remove event listeners
      this.tooltipTarget.removeEventListener("focusout", resetTooltip);
      this.tooltipTarget.removeEventListener("mouseout", resetTooltip);
    };
    this.tooltipTarget.addEventListener("focusout", resetTooltip);
    this.tooltipTarget.addEventListener("mouseout", resetTooltip);
  }

  _announce(message) {
    const status = document.getElementById(STATUS_ID);
    if (!status) return;
    // Cancel any pending update from an earlier copy
    clearTimeout(statusTimeout);
    // Clear first, so copying again re-announces the same message. The new
    // text is set after a short delay, as screen readers can miss a clear and
    // set that happen together and so not announce anything.
    status.textContent = "";
    statusTimeout = setTimeout(() => {
      status.textContent = message;
      // Clear once announced, so it isn't read out of context later
      statusTimeout = setTimeout(() => { status.textContent = ""; }, 3000);
    }, 100);
  }
}
