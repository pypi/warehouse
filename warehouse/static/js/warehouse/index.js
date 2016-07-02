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

// The nature of the web being what it is, we often will need to use Polyfills
// to get support for what we want. This will pull in babel-polyfill which will
// ensure we have an ES6 like environment.
import "babel-polyfill";

// We'll use docReady as a modern replacement for $(document).ready() which
// does not require all of jQuery to use. This will let us use it without
// having to load all of jQuery, which will make things faster.
import docReady from "warehouse/utils/doc-ready";

// Import our utility functions
import Analytics from "warehouse/utils/analytics";
import HTMLInclude from "warehouse/utils/html-include";
import * as formUtils from "warehouse/utils/forms";
import Clipboard from "clipboard";

// Kick off the client side HTML includes.
docReady(HTMLInclude);

// Trigger our analytics code.
docReady(Analytics);

// Handle the JS based automatic form submission.
docReady(formUtils.submitTriggers);

// Copy handler for the pip command on package detail page
docReady(() => {
  let setCopiedTooltip = (e) => {
    e.trigger.setAttribute("aria-label", "Copied!");
    e.clearSelection();
  };

  new Clipboard(".-js-copy-pip-command").on("success", setCopiedTooltip);
  new Clipboard(".-js-copy-sha256-link").on("success", setCopiedTooltip);

  // Get all elements with class "tooltipped" and bind to focousout and
  // mouseout events. Change the "aria-label" to "original-label" attribute
  // value.
  let setOriginalLabel = (element) => {
    element.setAttribute("aria-label", element.dataset.originalLabel);
  };
  let tooltippedElems = Array.from(document.querySelectorAll(".tooltipped"));
  tooltippedElems.forEach((element) => {
    element.addEventListener("focousout",
      setOriginalLabel.bind(undefined, element),
      false
    );
    element.addEventListener("mouseout",
      setOriginalLabel.bind(undefined, element),
      false
    );
  });
});
