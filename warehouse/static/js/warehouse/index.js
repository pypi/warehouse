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

// manually import IE11 Stimulus polyfills
// TODO: use @stimulus/polyfills once 1.1 is released https://github.com/stimulusjs/stimulus/pull/134
import "element-closest";
import "mutation-observer-inner-html-shim";

// Import stimulus
import { Application } from "stimulus";
import { definitionsFromContext } from "stimulus/webpack-helpers";

// We'll use docReady as a modern replacement for $(document).ready() which
// does not require all of jQuery to use. This will let us use it without
// having to load all of jQuery, which will make things faster.
import docReady from "warehouse/utils/doc-ready";

// Import our utility functions
import Analytics from "warehouse/utils/analytics";
import enterView from "enter-view";
import HTMLInclude from "warehouse/utils/html-include";
import * as formUtils from "warehouse/utils/forms";
import Clipboard from "clipboard";
import PositionWarning from "warehouse/utils/position-warning";
import Statuspage from "warehouse/utils/statuspage";
import timeAgo from "warehouse/utils/timeago";
import projectTabs from "warehouse/utils/project-tabs";
import searchFilterToggle from "warehouse/utils/search-filter-toggle";
import YouTubeIframeLoader from "youtube-iframe";
import RepositoryInfo from "warehouse/utils/repository-info";

// Human-readable timestamps for project histories
docReady(() => {
  timeAgo();
});

// project detail tabs
docReady(() => {
  projectTabs();
  window.addEventListener("resize", projectTabs, false);
});

// toggle search panel behavior
docReady(() => {
  if (document.querySelector(".-js-add-filter")) searchFilterToggle();
});

// Kick off the client side HTML includes.
docReady(HTMLInclude);

// Trigger our analytics code.
docReady(Analytics);

// Handle the JS based automatic form submission.
docReady(formUtils.submitTriggers);
docReady(formUtils.registerFormValidation);

docReady(Statuspage);

// Copy handler for
//   - the pip command on package detail page
//   - the copy hash on package detail page
//   - the copy hash on release maintainers page
docReady(() => {
  let setCopiedTooltip = (e) => {
    e.trigger.setAttribute("aria-label", "Copied!");
    e.clearSelection();
  };

  new Clipboard(".-js-copy-pip-command").on("success", setCopiedTooltip);
  new Clipboard(".-js-copy-hash").on("success", setCopiedTooltip);

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

// Close modals when escape button is pressed
docReady(() => {
  document.addEventListener("keydown", event => {
    if (event.keyCode === 27) {
      window.location.href = "#modal-close";
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

docReady(() => {
  if (document.querySelector(".-js-autoplay-when-visible")) {
    YouTubeIframeLoader.load((YT) => {
      enterView({
        selector: ".-js-autoplay-when-visible",
        trigger: (el) => {
          new YT.Player(el.id, {
            events: { "onReady": (e) => { e.target.playVideo(); } },
          });
        },
      });
    });
  }
});

docReady(() => {
  let changeRoleForms = document.querySelectorAll("form.change-role");

  if (changeRoleForms) {
    for (let form of changeRoleForms) {
      let changeButton = form.querySelector("button.change-button");
      let changeSelect = form.querySelector("select.change-field");

      changeSelect.addEventListener("change", function (event) {
        if (event.target.value === changeSelect.dataset.original) {
          changeButton.style.display = "none";
        } else {
          changeButton.style.display = "inline-block";
        }
      });
    }
  }
});

const application = Application.start();
const context = require.context("./controllers", true, /\.js$/);
application.load(definitionsFromContext(context));

docReady(() => {
  RepositoryInfo();
});
