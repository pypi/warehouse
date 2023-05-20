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
   * Get element's collasped status from the cookie.
   * @private
   */
  _getCollapsedCookie() {
    const id = this.data.get("identifier");
    const value = document.cookie.split(";").find(item => item.startsWith(`callout_block_${id}_collapsed=`));
    return value ? value.split("=")[1] : null;
  }

  /**
   * Set element's collapsed status as a cookie.
   * @private
   */
  _setCollapsedCookie(value) {
    if (this.data.get("setting") === "global")
      document.cookie = `callout_block_${this.data.get("identifier")}_collapsed=${value};path=/`;
    else
      document.cookie = `callout_block_${this.data.get("identifier")}_collapsed=${value}`;
  }

  initialize() {
    switch (this._getCollapsedCookie()) {
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
    this._setCollapsedCookie("1");
  }

  expand() {
    this.element.setAttribute("open", "");
    this._setCollapsedCookie("0");
  }

  save() {
    setTimeout(() => {
      if (!this.element.hasAttribute("open"))
        this._setCollapsedCookie("1");
      else
        this._setCollapsedCookie("0");
    }, 0);
  }
}
