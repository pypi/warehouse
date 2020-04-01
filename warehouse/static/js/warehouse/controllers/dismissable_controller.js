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
  /**
   * Get element's dismissed status from the cookie.
   * @private
   */
  _getDimissedFromCookie() {
    const id = this.data.get("identifier");
    const value = document.cookie.split(";").find(item => item.startsWith(`callout_block_${id}_dismissed=`));
    return value ? value.split("=")[1] : null;
  }

  initialize() {
    if (this._getDimissedFromCookie() == "1")
      this.dismiss();
  }

  dismiss() {
    this.element.classList.add("callout-block--dismissed");
    if (!this._getDimissedFromCookie())
      document.cookie = `callout_block_${this.data.get("identifier")}_dismissed=1`;
  }
}
