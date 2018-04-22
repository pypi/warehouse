import { Controller } from "stimulus";

export default class extends Controller {
  static targets = ["input", "preview", "submit"]

  update() {
    // Set the preview
    this.previewTarget.innerHTML = this.inputTarget.value;

    if (this.inputTarget.value.match(/^\w+(\s\w*)* :: \w+(\s\w*)*$/g)) {
      // Enable the submit button
      this.submitTarget.disabled = false;
    } else {
      this.submitTarget.disabled = true;
    }
  }
}
