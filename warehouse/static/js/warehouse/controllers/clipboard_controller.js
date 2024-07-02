/**
 * Licensed under the Apache License, Version 2.0 (the "License");
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
