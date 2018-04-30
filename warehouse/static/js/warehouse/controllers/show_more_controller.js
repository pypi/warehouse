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
  static targets = ["release", "showMoreButton"];

  // Initially set 5 projects to be visible.
  connect() {
    this.amountVisible = 5;
    this.releaseTargets
      .slice(this.amountVisible, this.releaseTargets.length)
      .forEach(element => (element.style.display = "none"));
  }

  // Increase amount visible during each button click event and check
  // if max amount visible has occurred and, if so, hide the button.
  addFive() {
    const previousAmountVisible = this.amountVisible;
    this.amountVisible = this.amountVisible + 5;
    this.releaseTargets
      .slice(previousAmountVisible, this.amountVisible)
      .forEach(element => (element.style.display = "block"));
    if (this.amountVisible === 20) {
      this.showMoreButtonTarget.style.display = "none";
    }
  }
}
