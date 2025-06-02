/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = ["saveButton"];
  static values = { current: String };

  change(event) {
    if (event.target.value === this.currentValue) {
      this.saveButtonTarget.style.visibility = "hidden";
    } else {
      this.saveButtonTarget.style.visibility = "visible";
    }
  }
}
