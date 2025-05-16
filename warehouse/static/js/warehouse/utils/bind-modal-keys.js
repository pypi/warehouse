/* SPDX-License-Identifier: Apache-2.0 */

export default () => {
  // Force tab key to cycle within the modal if the modal is active
  const keys = [];
  document.addEventListener("keydown", event => {
    const modalForm = document.querySelector(".modal:target .modal__form");
    keys[event.keyCode] = event.type === "keydown";

    if (modalForm && keys[9]) {
      // `firstItem` assumes that the close button is the first tabbable element.
      // `lastItem` assumes that `button.modal__action` is the confirm action and
      // `a.modal_action` is the cancel action (and that confirm is last when enabled).
      const firstItem = modalForm.querySelector(".modal__close");

      // This needs to be a function in order to get the disabled state in
      // case the user populates the confirm input.
      const getLastItem = () => modalForm.querySelector(
        ".modal__footer button.js-confirm").disabled
        ? modalForm.querySelector(".modal__footer .js-cancel")
        : modalForm.querySelector(".modal__footer .js-confirm");

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

  document.addEventListener("keyup", event => {
    keys[event.keyCode] = event.type === "keydown";
  });
};
