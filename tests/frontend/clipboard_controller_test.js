/* Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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
  });
});
