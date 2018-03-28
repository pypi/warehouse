import { Controller } from "stimulus";

export default class extends Controller {
  static targets = [
    "parent", "input", "preview", "submit",
  ]

  update() {
    // Set the preview
    this.previewTarget.innerHTML = [
      this.parentTarget.options[this.parentTarget.selectedIndex].text,
      this.inputTarget.value,
    ].join(" :: ");

    // Enable the input target
    this.inputTarget.disabled = !this.parentTarget.value;

    // Enable the submit button
    this.submitTarget.disabled = !(this.parentTarget.value && this.inputTarget.value);
  }
}
