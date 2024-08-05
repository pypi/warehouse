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

export default class extends Controller {
  static targets = ["prefilledTab", "tab", "tabPanel"];

  initialize() {
    // Select the tab with prefilled fields (if any)
    if (this.hasPrefilledTabTarget) {
      this.index = this.tabTargets.indexOf(this.prefilledTabTarget);
    }

    // Select the tab with errors if there are any
    this.tabPanelTargets.forEach((target, index) => {
      const aElement = target.querySelector("div#errors");
      if (aElement) {
        this.index = index;
      }
    });

    this.showTab();
  }

  change(e) {
    this.index = this.tabTargets.indexOf(e.target);
    this.showTab(this.index);
  }

  showTab() {
    this.tabPanelTargets.forEach((el, i) => {
      if (i == this.index) {
        el.classList.remove("is-hidden");
      } else {
        el.classList.add("is-hidden");
      }
    });

    this.tabTargets.forEach((el, i) => {
      if (i == this.index) {
        el.classList.add("is-active");
      } else {
        el.classList.remove("is-active");
      }
    });
  }

  get index() {
    return parseInt(this.data.get("index"));
  }

  set index(value) {
    this.data.set("index", value);
    this.showTab();
  }
}
