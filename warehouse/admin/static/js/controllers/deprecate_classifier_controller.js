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
  static targets = [
    "deprecatedClassifier", "alternativeClassifier"
  ]

  update() {
    const deprecatedClassifierId = this.deprecatedClassifierTarget.options[this.deprecatedClassifierTarget.selectedIndex].value;
    this.alternativeClassifierTargets.forEach(target => {
      const selectedAlternativeId = target.options[target.selectedIndex].value;

      // Reset the value to prevent self-selection.
      if (deprecatedClassifierId === selectedAlternativeId) {
        target.selectedIndex = 0;
      }

      // Disable deprecated classifier selection.
      for (let optionIndex = 0; optionIndex < target.options.length; ++optionIndex) {
        const option = target.options[optionIndex];
        option.disabled = option.value === deprecatedClassifierId || option.dataset.deprecated;
      }
    });
  }
}
