/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static targets = ["trigger", "content"];

  toggle() {
    if (this.contentTarget.classList.contains("display-block")) {
      this.close();
    } else {
      this.open();
    }
  }

  open() {
    this.contentTarget.classList.add("display-block");
    this.contentTarget.removeAttribute("aria-hidden");
    this.triggerTarget.setAttribute("aria-expanded", "true");
  }

  close() {
    this.hide();
    this.triggerTarget.focus();
  }

  // Bound to each radio's click action. event.detail tells us what
  // triggered it:
  // - 0: keyboard-synthesized (arrow-key nav, Space) - stay open, like
  //   browsing a native <select>
  // - >= 1: a real pointer click - close (Enter closes too, see keydown)
  selectOption(event) {
    if (event.detail === 0) {
      return;
    }
    this.close();
  }

  // Unlike close(), doesn't move focus - for when it has already moved on
  // its own (e.g. tabbing past the last option).
  hide() {
    this.contentTarget.classList.remove("display-block");
    this.contentTarget.setAttribute("aria-hidden", "true");
    this.triggerTarget.setAttribute("aria-expanded", "false");
  }

  focusout(event) {
    // Only reacts to a Tab-triggered focusout (see keydown). A mouse click
    // (e.g. on a <label>) causes its own transient blur/focus shuffle that
    // looks the same but isn't - reacting to it here would hide the
    // dropdown mid-click, before the label's click reaches its input.
    if (!this.tabKeyPressed) {
      return;
    }
    this.tabKeyPressed = false;

    if (!this.element.contains(event.relatedTarget)) {
      this.hide();
    }
  }

  keydown(event) {
    // While closed, let Enter on the trigger fall through natively
    // (-> click -> toggle#open). Only intervene once open.
    if (!this.contentTarget.classList.contains("display-block")) {
      return;
    }

    if (event.key === "Escape" || event.key === "Enter") {
      // Needed so the browser doesn't then treat Enter as activating the
      // trigger button once close() below focuses it, reopening what we
      // just closed.
      event.preventDefault();

      // Unlike Space, Enter doesn't natively select a radio. Do it here too:
      // - check it, so Enter both picks and closes
      // - fire `input` (Stimulus's default action event for an <input>,
      //   not `change`), so the filter-list controller reacts
      if (event.key === "Enter" && event.target.type === "radio" && !event.target.checked) {
        event.target.checked = true;
        event.target.dispatchEvent(new Event("input", { bubbles: true }));
        event.target.dispatchEvent(new Event("change", { bubbles: true }));
      }

      this.close();
    } else if (event.key === "Tab") {
      this.tabKeyPressed = true;
      // Safety net: Tab's focus shift is synchronous within this same
      // keydown, so a real focusout always arrives first and consumes
      // this. Only guards against focus not moving at all, so a later,
      // unrelated focusout isn't mistaken for one caused by Tab.
      setTimeout(() => {
        this.tabKeyPressed = false;
      }, 0);
    }
  }
}
