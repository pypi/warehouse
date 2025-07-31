/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";
import { gettext } from "../utils/messages-access";

export default class extends Controller {
  static targets = ["passwordMatch", "matchMessage", "submit"];

  connect() {
    this.checkPasswordsMatch();
  }

  checkPasswordsMatch() {
    if (this.passwordMatchTargets.some(field => field.value === "")) {
      this.matchMessageTarget.classList.add("hidden");
      this.submitTarget.setAttribute("disabled", "");
    } else {
      this.matchMessageTarget.classList.remove("hidden");
      if (this.passwordMatchTargets.every((field, i, arr) => field.value === arr[0].value)) {
        this.matchMessageTarget.textContent = gettext("Passwords match");
        this.matchMessageTarget.classList.add("form-error--valid");
        this.submitTarget.removeAttribute("disabled");
      } else {
        this.matchMessageTarget.textContent = gettext("Passwords do not match");
        this.matchMessageTarget.classList.remove("form-error--valid");
        this.submitTarget.setAttribute("disabled", "");
      }
    }
  }
}
