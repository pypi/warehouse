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
