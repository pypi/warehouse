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

    // Classifier is made up of words which can contain a-z, A-Z, 0-9,
    // underscore, hyphen, period, octothorp, plus, or parentheses
    var word_sub = "[\\w.\\(\\)\\+#-]";

    // Words can be repeated one or more times, separated by a space
    var words_sub = `${word_sub}+(\\s${word_sub}*)*`;

    // Classifer must have two parts, separated by a ' :: '
    var classifier_re = new RegExp(`^${words_sub} :: ${words_sub}$`);

    if (classifier_re.test(this.inputTarget.value)) {
      // Enable the submit button
      this.submitTarget.disabled = false;
    } else {
      this.submitTarget.disabled = true;
    }
  }
}
