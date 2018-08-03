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
  static targets = ["input", "preview", "submit"]

  update() {
    // Set the preview
    this.previewTarget.innerHTML = this.inputTarget.value;

    if (this.inputTarget.value.match(/^\w+(\s\w*)* :: \w+(\s\w*)*$/g)) {
      // Enable the submit button
      this.submitTarget.disabled = false;
    } else {
      this.submitTarget.disabled = true;
    }
  }
}
