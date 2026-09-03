/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  /**
   * Get the localStorage key holding this element's collapsed state.
   * @private
   */
  _storageKey() {
    return `callout_block_${this.data.get("identifier")}_collapsed`;
  }

  /**
   * Get element's collapsed status from localStorage.
   * @private
   */
  _getCollapsed() {
    return localStorage.getItem(this._storageKey());
  }

  /**
   * Persist element's collapsed status to localStorage.
   * @private
   */
  _setCollapsed(value) {
    localStorage.setItem(this._storageKey(), value);
  }

  initialize() {
    switch (this._getCollapsed()) {
      case "1":
        this.collapse();
        break;
      case "0":
        this.expand();
        break;
      default:
        this.save();
    }
  }

  collapse() {
    this.element.removeAttribute("open");
    this._setCollapsed("1");
  }

  expand() {
    this.element.setAttribute("open", "");
    this._setCollapsed("0");
  }

  save() {
    setTimeout(() => {
      if (!this.element.hasAttribute("open"))
        this._setCollapsed("1");
      else
        this._setCollapsed("0");
    }, 0);
  }
}
