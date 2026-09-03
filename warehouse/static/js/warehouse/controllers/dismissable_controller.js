/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  /**
   * Get the localStorage key holding this element's dismissed state.
   * @private
   */
  _storageKey() {
    return `callout_block_${this.data.get("identifier")}_dismissed`;
  }

  /**
   * Get element's dismissed status from localStorage.
   * @private
   */
  _getDismissed() {
    return localStorage.getItem(this._storageKey());
  }

  /**
   * Persist element's dismissed status to localStorage.
   * @private
   */
  _setDismissed(value) {
    localStorage.setItem(this._storageKey(), value);
  }

  initialize() {
    if (this._getDismissed() === "1")
      this.dismiss();
  }

  dismiss() {
    this.element.classList.add("callout-block--dismissed");
    this._setDismissed("1");
  }
}
