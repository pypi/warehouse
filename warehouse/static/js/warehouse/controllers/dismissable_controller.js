/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  /**
   * Get element's dismissed status from the cookie.
   * @private
   */
  _getDismissedCookie() {
    const id = this.data.get("identifier");
    // `document.cookie` joins pairs with "; ", so every segment but the first
    // has a leading space to strip before matching.
    const value = document.cookie
      .split(";")
      .map(item => item.trim())
      .find(item => item.startsWith(`callout_block_${id}_dismissed=`));
    return value ? value.split("=")[1] : null;
  }

  /**
   * Set element's dismissed status as a cookie.
   * @private
   */
  _setDismissedCookie(value) {
    let cookie = `callout_block_${this.data.get("identifier")}_dismissed=${value}`;
    if (this.data.get("setting") === "global")
      cookie += ";path=/";
    if (this.data.get("maxAge"))
      cookie += `;max-age=${this.data.get("maxAge")}`;
    document.cookie = cookie;
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
