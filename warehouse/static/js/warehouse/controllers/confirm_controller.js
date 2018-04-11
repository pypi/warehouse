import { Controller } from "stimulus";

export default class extends Controller {
  static targets = [ "input", "button" ]

  initialize() {
    // Force tab key to cycle within the modal if the modal is active
    let keys = [];
    this.element.addEventListener("keydown", event => {
      let modalForm = this.element.querySelector(".modal:target .modal__form");
      keys[event.keyCode] = event.type === "keydown";

      if (modalForm && keys[9]) {
        // `firstItem` assumes that the close button is the first tabbable element.
        // `lastItem` assumes that `button.modal__action` is the confirm action and
        // `a.modal_action` is the cancel action (and that confirm is last when enabled).
        const firstItem = modalForm.querySelector(".modal__close");

        // This needs to be a function in order to get the disabled state in
        // case the user populates the confirm input.
        const getLastItem = () => modalForm.querySelector(".modal__footer button.modal__action").disabled
          ? modalForm.querySelector(".modal__footer a.modal__action")
          : modalForm.querySelector(".modal__footer button.modal__action");

        // Handle SHIFT+TAB
        if (keys[9] && keys[16]) {
          if (document.activeElement === firstItem) {
            getLastItem().focus();
            event.preventDefault();
          }
        } else if (keys[9]) {
          if (document.activeElement === getLastItem()) {
            firstItem.focus();
            event.preventDefault();
          }
        }
      }
    });

    this.element.addEventListener("keyup", event => {
      keys[event.keyCode] = event.type === "keydown";
    });
  }

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
