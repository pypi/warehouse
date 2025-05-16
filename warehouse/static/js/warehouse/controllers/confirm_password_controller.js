/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = [ "button", "password", "showPassword" ];

  connect() {
    this.buttonTarget.disabled = true;
    this.setPasswordVisibility();
    // In case the browser beat us to it (e.g. Firefox Password Manager)
    this.check();
  }

  setPasswordVisibility() {
    this.passwordTarget.type = this.showPasswordTarget.checked ? "text" : "password";
  }

  check() {
    this.buttonTarget.disabled = this.passwordTarget.value.trim() === "";
  }
}
