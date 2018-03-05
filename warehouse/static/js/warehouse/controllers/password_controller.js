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
  static targets = ["showPassword", "newPassword", "passwordConfirm"];
  passwordFields = ["newPasswordTarget", "passwordConfirmTarget"];

  showPasswords() {
    const showPassword = this.showPasswordTarget;
    for (let field of this.passwordFields) {
      if (showPassword.checked) {
        this[field].type = "text";
      } else {
        this[field].type = "password";
      }
    }
  }
}
