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
import * as cookie from "cookie";
import { Controller } from "stimulus";

export default class extends Controller {
  static targets = ["notification", "notificationDismiss"];
  expireDays = 30;
  dismissKey = "dismissed";

  connect() {
    const cookies = cookie.parse(document.cookie);
    if (this.dismissKey in cookies && cookies[this.dismissKey]) {
      this.notificationTarget.style.display = "none";
    }
  }

  dismiss() {
    this.notificationTarget.style.display = "none";
    const expires = new Date(Date.now() + this.expireDays * 864e5).toUTCString();
    document.cookie = `${this.dismissKey}=1;expires=${expires};path=/`;
  }
}