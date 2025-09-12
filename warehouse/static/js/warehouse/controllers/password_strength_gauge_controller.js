/* SPDX-License-Identifier: Apache-2.0 */

/* global zxcvbn */

import { Controller } from "@hotwired/stimulus";
import { gettext } from "../utils/messages-access";

export default class extends Controller {
  static targets = ["password", "strengthGauge"];

  checkPasswordStrength() {
    let password = this.passwordTarget.value;
    if (password === "") {
      this.strengthGaugeTarget.setAttribute("class", "password-strength__gauge");
      this.setScreenReaderMessage(gettext("Password field is empty"));
    } else {
      // following recommendations on the zxcvbn JS docs
      // the zxcvbn function is available by loading `vendor/zxcvbn.js`
      // in the register, account and reset password templates
      let zxcvbnResult = zxcvbn(password.substring(0, 100));
      this.strengthGaugeTarget.setAttribute("class", `password-strength__gauge password-strength__gauge--${zxcvbnResult.score}`);
      this.strengthGaugeTarget.setAttribute("data-zxcvbn-score", zxcvbnResult.score);

      const feedbackSuggestions = zxcvbnResult.feedback.suggestions.join(" ");
      if (feedbackSuggestions) {
        // Note: we can't localize this string because it will be mixed
        // with other non-localizable strings from zxcvbn
        this.setScreenReaderMessage("Password is too easily guessed. " + feedbackSuggestions);
      } else {
        this.setScreenReaderMessage(gettext("Password is strong"));
      }
    }
  }

  setScreenReaderMessage(msg) {
    this.strengthGaugeTarget.querySelector(".sr-only").textContent = msg;
  }
}
