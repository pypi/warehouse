/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = ["termsOfServiceAccepted", "submit"];

  connect() {
    this.checkTermsOfServiceAccepted();
  }

  checkTermsOfServiceAccepted() {
    if (this.termsOfServiceAcceptedTarget.checked) {
      this.submitTarget.removeAttribute("disabled");
    } else {
      this.submitTarget.setAttribute("disabled", "");
    }
  }
}
