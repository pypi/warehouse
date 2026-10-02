/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it, jest */

import { Application } from "@hotwired/stimulus";
import ClipboardController from "../../warehouse/static/js/warehouse/controllers/clipboard_controller";

// Create a mock clipboard object, since jsdom doesn't support the clipboard API
// See https://github.com/jsdom/jsdom/issues/1568
Object.defineProperty(navigator, "clipboard", {
  writable: true,
  value: {
    writeText: jest.fn(),
  },
});


const clipboardContent = `
  <div data-controller="clipboard">
    <span id="#id" data-clipboard-target="source">Copyable Thing</span>
    <button
      type="button"
      class="copy-tooltip"
      data-action="clipboard#copy"
      data-clipboard-target="tooltip"
      data-clipboard-tooltip-value="Copy to clipboard"
    >
      <i class="fa fa-copy" aria-hidden="true"></i>
    </button>
  </div>
`;

describe("ClipboardController", () => {
  beforeEach(() => {
    document.body.innerHTML = clipboardContent;
    window.plausible = jest.fn();
    const application = Application.start();
    application.register("clipboard", ClipboardController);
  });

  describe("copy", () => {
    it("copies text to clipboard and resets", () => {
      const button = document.querySelector(".copy-tooltip");
      expect(button.dataset.clipboardTooltipValue).toEqual("Copy to clipboard");

      button.click();

      // Check that the text was copied to the clipboard
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("Copyable Thing");
      // Check that the tooltip text was changed
      expect(button.dataset.clipboardTooltipValue).toEqual("Copied");

      button.dispatchEvent(new FocusEvent("focusout"));

      // Check that the tooltip text was reset
      expect(button.dataset.clipboardTooltipValue).toEqual("Copy to clipboard");
    });

    it("tracks the configured plausible event", () => {
      document.querySelector("[data-controller='clipboard']")
        .dataset.clipboardPlausibleEventValue = "Copy Project Install Command";
      const button = document.querySelector(".copy-tooltip");

      button.click();

      expect(window.plausible).toHaveBeenCalledWith("Copy Project Install Command");
    });

    it("does not track when there is no configured plausible event", () => {
      const button = document.querySelector(".copy-tooltip");

      button.click();

      expect(window.plausible).not.toHaveBeenCalled();
    });
  });
});
