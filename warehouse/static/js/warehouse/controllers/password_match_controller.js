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

import { Controller } from "stimulus";

export default class extends Controller {
  static targets = ["passwordMatch", "matchMessage", "submit"];

  connect() {
    this.checkPasswordsMatch();
  }

  checkPasswordsMatch() {
    if (this.passwordMatchTargets.every(field => field.value === "")) {
      this.matchMessageTarget.classList.add("hidden");
      this.submitTarget.setAttribute("disabled", "");
    } else {
      this.matchMessageTarget.classList.remove("hidden");
      if (this.passwordMatchTargets.every((field, i, arr) => field.value === arr[0].value)) {
        this.matchMessageTarget.textContent = "Passwords match";
        this.matchMessageTarget.classList.add("form-error--valid");
        this.submitTarget.removeAttribute("disabled");
      } else {
        this.matchMessageTarget.textContent = "Passwords do not match";
        this.matchMessageTarget.classList.remove("form-error--valid");
        this.submitTarget.setAttribute("disabled", "");
      }
    }
  }
}
