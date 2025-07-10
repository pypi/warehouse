/* SPDX-License-Identifier: Apache-2.0 */

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
