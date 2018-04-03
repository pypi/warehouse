/**
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/* global zxcvbn */

import { Controller } from "stimulus";

export default class extends Controller {
  static targets = ["password", "strengthGauge"];

  checkPasswordStrength() {
    let password = this.passwordTarget.value;
    if (password === "") {
      this.strengthGaugeTarget.setAttribute("class", "password-strength__gauge");
      this.setScreenReaderMessage("Password field is empty");
    } else {
      // following recommendations on the zxcvbn JS docs
      // the zxcvbn function is available by loading `vendor/zxcvbn.js`
      // in the register, account and reset password templates
      let zxcvbnResult = zxcvbn(password);
      this.strengthGaugeTarget.setAttribute("class", `password-strength__gauge password-strength__gauge--${zxcvbnResult.score}`);
      this.strengthGaugeTarget.setAttribute("data-zxcvbn-score", zxcvbnResult.score);
      this.setScreenReaderMessage(zxcvbnResult.feedback.suggestions.join(" ") || "Password is strong");
    }
  }

  setScreenReaderMessage(msg) {
    this.strengthGaugeTarget.querySelector(".sr-only").innerHTML = msg;
  }
}
