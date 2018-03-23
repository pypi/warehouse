import { Controller } from "stimulus";

export default class extends Controller {
  static targets = [ "input", "button" ]

  connect() {
    this.buttonTarget.disabled = true;
  }

  cancel() {
    this.inputTarget.value = "";
    this.buttonTarget.disabled = true;
  }

  check() {
    if (this.inputTarget.value == this.buttonTarget.dataset.expected) {
      this.buttonTarget.disabled = false;
    } else {
      this.buttonTarget.disabled = true;
    }
  }
}
