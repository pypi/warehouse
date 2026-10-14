/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = [ "input", "button" ];

  cancel() {
    // Cancel button is a button (not an `a`) so we need to do close the
    // modal manually
    window.location.href = "#modal-close";
    // The close link sits outside the form, so reset it to clear checkboxes
    this.element.querySelector("form")?.reset();
    this.inputTarget.value = "";
    this.buttonTarget.disabled = true;
  }
}
