/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, afterEach, beforeEach, describe, it, jest */

import { Application } from "@hotwired/stimulus";
import ClipboardController from "../../warehouse/static/js/warehouse/controllers/clipboard_controller";

// Create a mock clipboard object, since jsdom doesn't support the clipboard API
// See https://github.com/jsdom/jsdom/issues/1568
Object.defineProperty(navigator, "clipboard", {
  writable: true,
  value: {
    writeText: jest.fn(() => Promise.resolve()),
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
  let application;

  beforeEach(() => {
    document.body.innerHTML = clipboardContent;
    window.plausible = jest.fn();
    application = Application.start();
    application.register("clipboard", ClipboardController);
  });

  afterEach(() => {
    // Otherwise each test's application stays connected and copies again
    application.stop();
    // Restore real timers even if a test using fake timers fails
    jest.useRealTimers();
  });

  describe("connect", () => {
    it("adds a single shared status region to the page", async () => {
      document.body.insertAdjacentHTML("beforeend", clipboardContent);
      // Let Stimulus connect the second controller
      await Promise.resolve();
      expect(document.querySelectorAll("[data-controller='clipboard']")).toHaveLength(2);
      expect(document.querySelectorAll("#clipboard-status")).toHaveLength(1);
    });
  });

  describe("copy", () => {
    it("copies text to clipboard and resets", async () => {
      const button = document.querySelector(".copy-tooltip");
      expect(button.dataset.clipboardTooltipValue).toEqual("Copy to clipboard");

      button.click();
      // Let the clipboard write resolve
      await Promise.resolve();

      // Check that the text was copied to the clipboard
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("Copyable Thing");
      // Check that the tooltip text was changed
      expect(button.dataset.clipboardTooltipValue).toEqual("Copied");

      button.dispatchEvent(new FocusEvent("focusout"));

      // Check that the tooltip text was reset
      expect(button.dataset.clipboardTooltipValue).toEqual("Copy to clipboard");
    });

    it("announces the copy in a status region", async () => {
      jest.useFakeTimers();
      const button = document.querySelector(".copy-tooltip");
      const status = document.getElementById("clipboard-status");
      expect(status).toHaveAttribute("role", "status");
      expect(status).toHaveClass("sr-only");

      button.click();
      await Promise.resolve();
      expect(status.textContent).toEqual("");
      jest.advanceTimersByTime(100);
      expect(status.textContent).toEqual("Copied");
      jest.advanceTimersByTime(3000);
      expect(status.textContent).toEqual("");
    });

    it("re-announces when copying again", async () => {
      jest.useFakeTimers();
      const button = document.querySelector(".copy-tooltip");
      const status = document.getElementById("clipboard-status");

      button.click();
      await Promise.resolve();
      jest.advanceTimersByTime(100);
      expect(status.textContent).toEqual("Copied");
      jest.advanceTimersByTime(1000);

      button.click();
      await Promise.resolve();
      // Cleared, so the same message is announced again
      expect(status.textContent).toEqual("");
      jest.advanceTimersByTime(100);
      expect(status.textContent).toEqual("Copied");
      // The first copy's pending clear was cancelled
      jest.advanceTimersByTime(2000);
      expect(status.textContent).toEqual("Copied");
    });

    it("does not claim success when the clipboard write fails", async () => {
      jest.useFakeTimers();
      navigator.clipboard.writeText.mockRejectedValueOnce(new Error("denied"));
      const button = document.querySelector(".copy-tooltip");
      const status = document.getElementById("clipboard-status");

      button.click();
      await Promise.resolve();
      jest.runAllTimers();

      expect(button.dataset.clipboardTooltipValue).toEqual("Copy to clipboard");
      expect(status.textContent).toEqual("");
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
