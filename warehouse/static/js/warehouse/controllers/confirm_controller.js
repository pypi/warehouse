import { Controller } from "stimulus";

export default class extends Controller {
  static targets = [ "input", "button" ]

  /**
   * Returns first item in modal. This currently usually the close button.
   */
  getFirstItem() {
    return this.element.querySelector(".modal__close");
  }

  /**
   * Returns the last item in modal.
   * This assumes that `button.modal__action` is the confirm action and
   * `a.modal__action` is the cancel action.
   */
  getLastItem() {
    return this.element.querySelector(
      ".modal__footer button.modal__action").disabled
      ? this.element.querySelector(".modal__footer a.modal__action")
      : this.element.querySelector(".modal__footer button.modal__action")
  }

  handleFirstItemTab() {
    const _this = this;
    this.getFirstItem().addEventListener("keydown", event => {
      _this.keys[event.keyCode] = event.type === "keydown";
      // Handle SHIFT+TAB
      if (_this.keys[9] && _this.keys[16]) {
        _this.getLastItem().focus();
        event.preventDefault();
      }
    });

    this.getFirstItem().addEventListener("keyup", event => {
      _this.keys[event.keyCode] = event.type === "keydown";
    });
  }

  handleLastItemTab () {
    const _this = this;
    const elements = [
      this.element.querySelector(".modal__footer a.modal__action"),
      this.element.querySelector(".modal__footer button.modal__action"),
    ];

    elements.map(el => {
      el.addEventListener("keydown", function (event) {
        _this.keys[event.keyCode] = event.type === "keydown";

        // Check if this is really the last item first
        if (event.target === _this.getLastItem()) {
          if (_this.keys[9] && !_this.keys[16]) {
            _this.getFirstItem().focus();
            event.preventDefault();
          }
        }
      });

      el.addEventListener("keyup", event => {
        _this.keys[event.keyCode] = event.type === "keydown";
      });
    });
  }

  initialize() {
    this.keys = [];
    this.handleFirstItemTab();
    this.handleLastItemTab();
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
