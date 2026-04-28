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
    // Bind once and store the reference so removeEventListener can match it
    // on disconnect (each .bind() call returns a *new* function).
    this.boundCheck = this.check.bind(this);
    this.formTarget.addEventListener("submit", this.boundCheck);
  }

  disconnect() {
    this.formTarget.removeEventListener("submit", this.boundCheck);
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
