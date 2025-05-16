/* SPDX-License-Identifier: Apache-2.0 */

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
