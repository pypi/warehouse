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
  static targets = ["trendingProject", "addFiveButton"];

  connect() {
    // Initially set 5 projects to be visible
    let i = 0;
    this.amountVisible = 5;
    for (let element of this.trendingProjectTargets) {
      if(i >= this.amountVisible) {
        element.style.display = "none";
      } 
      i++;
    }
  }

  // Increase amount visible during each button click event
  addFive() {
    let i = this.amountVisible;
    this.amountVisible = this.amountVisible + 5;
    for (; i < this.amountVisible; i++) {
      this.trendingProjectTargets[i].style.display = "block";
    }
    if(i >= 20) {
      this.addFiveButtonTarget.style.display = "none";
    }
  }
}
