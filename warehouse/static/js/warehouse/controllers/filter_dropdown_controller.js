/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = ["trigger", "content"];

  toggle() {
    if (this.contentTarget.classList.contains("display-block")) {
      this.close();
    } else {
      this.open();
    }
  }

  open() {
    this.contentTarget.classList.add("display-block");
    this.contentTarget.removeAttribute("aria-hidden");
    this.triggerTarget.setAttribute("aria-expanded", "true");
  }

  close() {
    this.contentTarget.classList.remove("display-block");
    this.contentTarget.setAttribute("aria-hidden", "true");
    this.triggerTarget.setAttribute("aria-expanded", "false");
  }
}
