/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

const selectedClass = "attestations-viewer__file-item--is-selected";

export default class extends Controller {
  static targets = ["item", "content"];

  select(event) {
    const item = event.currentTarget.closest("[data-attestations-viewer-target='item']");
    const filename = item.dataset.filename;
    this._selectFilename(filename);
  }

  _selectFilename(filename) {
    this.itemTargets.forEach(item => {
      const isSelected = item.dataset.filename === filename;
      item.classList.toggle(selectedClass, isSelected);
      item.querySelector("button").setAttribute("aria-pressed", isSelected ? "true" : "false");
    });

    this.contentTargets.forEach(content => {
      const isSelected = content.dataset.filename === filename;
      content.classList.toggle("hidden", !isSelected);

      // Only the visible panel's checksums need a live clipboard controller;
      // toggling this attribute connects/disconnects it via Stimulus's DOM observer.
      content.querySelectorAll(".attestation__checksum").forEach(checksum => {
        if (isSelected) {
          checksum.setAttribute("data-controller", "clipboard");
        } else {
          checksum.removeAttribute("data-controller");
        }
      });
    });
  }
}
