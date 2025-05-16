/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  /**
   * Get element's dismissed status from the cookie.
   * @private
   */
  _getDismissedCookie() {
    const id = this.data.get("identifier");
    const value = document.cookie.split(";").find(item => item.startsWith(`callout_block_${id}_dismissed=`));
    return value ? value.split("=")[1] : null;
  }

  /**
   * Set element's dismissed status as a cookie.
   * @private
   */
  _setDismissedCookie(value) {
    if (this.data.get("setting") === "global")
      document.cookie = `callout_block_${this.data.get("identifier")}_dismissed=${value};path=/`;
    else
      document.cookie = `callout_block_${this.data.get("identifier")}_dismissed=${value}`;
  }

  initialize() {
    if (this._getDismissedCookie() === "1")
      this.dismiss();
  }

  dismiss() {
    this.element.classList.add("callout-block--dismissed");
    this._setDismissedCookie("1");
  }
}
