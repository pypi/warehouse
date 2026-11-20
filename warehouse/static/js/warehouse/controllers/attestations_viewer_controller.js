/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

const selectedClass = "attestations-viewer__file-item--is-selected";

export default class extends Controller {
  static targets = ["item", "content", "empty"];

  select(event) {
    const item = event.currentTarget.closest("[data-attestations-viewer-target='item']");
    const filename = item.dataset.filename;
    this._selectFilename(filename);
  }

  /**
   * Select the first item not hidden by the filter-list controller, or show the empty state
   * if none are visible. Called by the filter-list controller (a sibling on this same
   * element) after it filters the file list.
   */
  selectFirstVisible() {
    const selected = this.itemTargets.find(item => item.classList.contains(selectedClass));
    if (selected && !selected.classList.contains("hidden")) {
      // The current selection is still visible: leave it as-is rather than
      // jumping back to the first visible item on every unrelated filter change.
      return;
    }

    const visibleItem = this.itemTargets.find(item => !item.classList.contains("hidden"));
    if (visibleItem) {
      this._selectFilename(visibleItem.dataset.filename);
    } else {
      this._showEmpty();
    }
  }

  _selectFilename(filename) {
    if (this.hasEmptyTarget) {
      this.emptyTarget.classList.add("hidden");
    }

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

  _showEmpty() {
    this.itemTargets.forEach(item => {
      item.classList.remove(selectedClass);
      item.querySelector("button").setAttribute("aria-pressed", "false");
    });
    this.contentTargets.forEach(content => content.classList.add("hidden"));
    if (this.hasEmptyTarget) {
      this.emptyTarget.classList.remove("hidden");
    }
  }
}
