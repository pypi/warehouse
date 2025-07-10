/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";
import { gettext } from "../utils/messages-access";

// Copy handler for copy tooltips, e.g.
//   - the pip command on package detail page
//   - the copy hash on package detail page
//   - the copy hash on release maintainers page

// See `warehouse/static/sass/blocks/_copy-tooltip.scss` for style details.
export default class extends Controller {
  static targets = [ "source", "tooltip" ];

  copy() {
    // save the original tooltip text
    const clipboardTooltipOriginalValue = this.tooltipTarget.dataset.clipboardTooltipValue;
    // copy the source text to clipboard
    navigator.clipboard.writeText(this.sourceTarget.textContent);
    // set the tooltip text
    this.tooltipTarget.dataset.clipboardTooltipValue = gettext("Copied");

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
}
