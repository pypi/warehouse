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
  static targets = [ "input", "button" ]

  connect() {
    this.buttonTarget.disabled = true;
  }

  cancel() {
    // Cancel button is a button (not an `a`) so we need to do close the
    // modal manually
    window.location.href = "#modal-close";
    this.inputTarget.value = "";
    this.buttonTarget.disabled = true;
  }

  check() {
    if (this.inputTarget.value.toLowerCase() === this.buttonTarget.dataset.expected.toLowerCase()) {
      this.buttonTarget.disabled = false;
    } else {
      this.buttonTarget.disabled = true;
    }
  }
}
