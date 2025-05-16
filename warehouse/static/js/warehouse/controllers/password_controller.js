/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = ["showPassword", "password"];

  connect() {
    // Reset these so they don't persist between page reloads
    // We assume that both targets above exist
    this.showPasswordTarget.checked = false;
    this.togglePasswords();
  }

  togglePasswords() {
    for (let field of this.passwordTargets) {
      field.type = this.showPasswordTarget.checked ? "text" : "password";
    }
  }
}
