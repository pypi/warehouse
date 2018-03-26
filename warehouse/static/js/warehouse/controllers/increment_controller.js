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
  static targets = ["button"];

  // Initially set default to 5 projects visible
  constructor() {
    super();
    this.trending_visible = 5;
    this.latest_visible = 5;
  }
  // Increase amount visible during each click event of Show More button
  addFive(e) {
    const eventType = e.target.value;
    const elements = document.getElementsByClassName(
      `hide-by-index-${eventType}`
    );
    // j is previous amount visible, end is how many will be visible
    let j = this[`${eventType}_visible`];
    const end = (this[`${eventType}_visible`] += 5);
    if (end <= 20) {
      for (; j < end; j++) {
        if (elements[j]) {
          elements[j].style.display = "block";
        }
      }
      // Hide Show More button when max amount is visible
      if (end === 20) {
        document.getElementById(`increment-button-${eventType}`).style.display =
          "none";
      }
    }
  }
}
