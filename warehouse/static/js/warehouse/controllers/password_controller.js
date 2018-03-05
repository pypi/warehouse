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
