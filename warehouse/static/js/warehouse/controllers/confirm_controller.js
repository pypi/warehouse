/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = ["input", "button", "checkbox"];

  connect() {
    this.buttonTarget.disabled = true;
  }

  checkCheckboxes() {
    // Check if all checkbox targets have been checked. If there are no checkboxes defined to check,
    // this will return true.
    if (this.checkboxTargets && this.checkboxTargets.length > 0) {
      return this.checkboxTargets.every((input) => input.checked);
    } else {
      return true;
    }
  }

  checkInputString() {
    // Check if the current value of the input text field matches what we expect it to. If so, this
    // will return true
    return (
      this.inputTarget.value.toLowerCase() ===
      this.buttonTarget.dataset.expected.toLowerCase()
    );
  }

  check() {
    if (this.checkCheckboxes() && this.checkInputString()) {
      this.buttonTarget.disabled = false;
    } else {
      this.buttonTarget.disabled = true;
    }
  }
}
