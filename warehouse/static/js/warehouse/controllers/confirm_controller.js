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

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = ["input", "button", "checkbox"];

  connect() {
    this.buttonTarget.disabled = true;
  }

  checkCheckboxes() {
    // Check if all checkbox targets have been checked. If there are no checkboxes defined to check,
    // this will return true.
    if (this.checkboxTargets && this.checkboxTargets.length > 0) {
      return this.checkboxTargets.every((input) => input.checked);
    } else {
      return true;
    }
  }

  checkInputString() {
    // Check if the current value of the input text field matches what we expect it to. If so, this
    // will return true
    return (
      this.inputTarget.value.toLowerCase() ===
      this.buttonTarget.dataset.expected.toLowerCase()
    );
  }

  check() {
    if (this.checkCheckboxes() && this.checkInputString()) {
      this.buttonTarget.disabled = false;
    } else {
      this.buttonTarget.disabled = true;
    }
  }
}
