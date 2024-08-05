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
  static targets = ["searchField"];

  focusSearchField(event) {
    // When we receive a keydown event, check if it's `/` and that we're not
    // already focused on the search field, or any other input field.
    if (event.key === "/" && event.target.tagName !== "INPUT" && event.target.tagName !== "TEXTAREA") {
      // Prevent the key from being handled as an actual input
      event.preventDefault();
      this.searchFieldTarget.focus();
    }
  }
}
