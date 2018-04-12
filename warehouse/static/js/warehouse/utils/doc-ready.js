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

import unsupportedBrowser from "./unsupported_browser";

let warningShown = false;

function showUnsupportedBrowserWarning() {
  if (document.getElementById("unsupported-browser") !== null) return;

  let warning_html = "<div id='unsupported-browser' class='notification-bar notification-bar--danger'><span class='notification-bar__icon'><i class='fa fa-exclamation-triangle' aria-hidden='true'></i><span class='sr-only'>Warning:</span></span><span class='notification-bar__message'>You are using an unsupported browser, please upgrade to a newer version.</span></div>";
  let warning_div = document.createElement("div");
  warning_div.innerHTML = warning_html;

  let warning_section = document.getElementById("sticky-notifications");
  warning_section.appendChild(warning_div);
  warningShown = true;
}

export default (fn) => {
  if (unsupportedBrowser) {
    if (!warningShown) {
      document.addEventListener("DOMContentLoaded", showUnsupportedBrowserWarning);
    }
    return;
  }
  if (document.readyState != "loading") { fn(); }
  else { document.addEventListener("DOMContentLoaded", fn); }
};
