/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = [ "input", "button" ];

  connect() {
    this.buttonTarget.setAttribute("disabled", "");
  }

  check() {
    if (this.inputTargets.every(input => input.checked)) {
      this.buttonTarget.removeAttribute("disabled");
    } else {
      this.buttonTarget.setAttribute("disabled", "");
    }
  }
}
