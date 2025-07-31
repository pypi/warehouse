/* SPDX-License-Identifier: Apache-2.0 */

/**
 * This controller handles the confirmation dialog that appears
 * when a user submits their email address during registration.
 * It ensures that the user confirms their email
 * before proceeding with the form submission.
 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = ["dialog", "email", "form"];

  connect() {
    this.formTarget.addEventListener("submit", this.check.bind(this));
  }

  disconnect() {
    this.formTarget.removeEventListener("submit", this.check.bind(this));
  }

  check(event) {
    if (this.data.get("confirmed") === "true") {
      return;
    }

    event.preventDefault();
    this.emailTarget.textContent = this.emailValue;
    this.dialogTarget.showModal();
  }

  close() {
    this.dialogTarget.close();
  }

  confirm(event) {
    event.preventDefault();
    this.data.set("confirmed", "true");
    this.formTarget.requestSubmit();
  }

  get emailValue() {
    return this.formTarget.querySelector("input[type='email']").value;
  }
}
