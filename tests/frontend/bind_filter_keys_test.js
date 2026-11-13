/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeAll, beforeEach, afterEach, describe, it, jest */

import bindFilterKeys from "../../warehouse/static/js/warehouse/utils/bind-filter-keys";

// Mirrors the classifier filter panel in templates/search/results.html:
// a close button, then one accordion per top-level classifier, each holding
// a (possibly nested) tree of checkbox inputs.
const panelHTML = `
<div class="filter-panel -js-filter-panel">
  <button type="button" class="filter-panel__close -js-close-panel">Close</button>
  <form id="classifiers">
    <div class="accordion accordion--closed">
      <button type="button" class="accordion__link">Topic</button>
      <div class="accordion__content">
        <ul>
          <li><input type="checkbox" id="topic-1"></li>
        </ul>
      </div>
    </div>
    <div class="accordion" id="last-accordion">
      <button type="button" class="accordion__link" id="last-accordion-link">Typing</button>
      <div class="accordion__content">
        <ul>
          <li><input type="checkbox" id="typing-a">
            <ul>
              <li><input type="checkbox" id="typing-a1"></li>
              <li><input type="checkbox" id="typing-a2"></li>
            </ul>
          </li>
          <li><input type="checkbox" id="typing-b"></li>
        </ul>
      </div>
    </div>
  </form>
</div>
<a href="/search/?q=x" id="first-result">A result</a>`;

const keyEvent = (type, keyCode) => {
  const event = new window.KeyboardEvent(type, {bubbles: true, cancelable: true});
  Object.defineProperty(event, "keyCode", {value: keyCode});
  return document.dispatchEvent(event);
};
const keydown = keyCode => keyEvent("keydown", keyCode);
const keyup = keyCode => keyEvent("keyup", keyCode);
const tab = () => { const notPrevented = keydown(9); keyup(9); return notPrevented; };
const shiftTab = () => {
  keydown(16);
  const notPrevented = keydown(9);
  keyup(9);
  keyup(16);
  return notPrevented;
};

describe("bind filter keys util", () => {
  // The listeners query the DOM on every event, so bind once and rebuild
  // the panel markup for each test.
  beforeAll(() => {
    bindFilterKeys();
  });

  beforeEach(() => {
    document.body.innerHTML = panelHTML;
  });

  afterEach(() => {
    keyup(9);
    keyup(16);
    keyup(27);
  });

  describe("when the panel has not been opened", () => {
    // The static sidebar on larger viewports: no inline display style.
    it("does not trap tab at the bottom of the classifiers list", () => {
      const lastItem = document.getElementById("typing-b");
      lastItem.focus();
      expect(tab()).toEqual(true); // not preventDefault()ed
      expect(document.activeElement).toEqual(lastItem);
    });

    it("does not trap tab partway through a nested classifier tree", () => {
      const nestedItem = document.getElementById("typing-a2");
      nestedItem.focus();
      expect(tab()).toEqual(true);
      expect(document.activeElement).toEqual(nestedItem);
    });

    it("does not trap shift+tab on the close button", () => {
      const closeButton = document.querySelector(".filter-panel__close");
      closeButton.focus();
      expect(shiftTab()).toEqual(true);
      expect(document.activeElement).toEqual(closeButton);
    });

    it("does not close the panel on escape", () => {
      const closeButton = document.querySelector(".filter-panel__close");
      const clickSpy = jest.spyOn(closeButton, "click");
      keydown(27);
      keyup(27);
      expect(clickSpy).not.toHaveBeenCalled();
    });
  });

  describe("when the panel is open as an overlay", () => {
    beforeEach(() => {
      // search-filter-toggle.js opens the panel with an inline display.
      document.querySelector(".filter-panel").style.display = "block";
    });

    it("cycles tab from the last item back to the close button", () => {
      const lastItem = document.getElementById("typing-b");
      lastItem.focus();
      expect(tab()).toEqual(false); // preventDefault()ed
      expect(document.activeElement).toEqual(
        document.querySelector(".filter-panel__close"));
    });

    it("cycles shift+tab from the close button to the last item", () => {
      const closeButton = document.querySelector(".filter-panel__close");
      closeButton.focus();
      expect(shiftTab()).toEqual(false);
      expect(document.activeElement).toEqual(
        document.getElementById("typing-b"));
    });

    it("does not stop tabbing at nested tree items before the last item", () => {
      // The old `li:last-child` lookup picked typing-a2 here.
      const nestedItem = document.getElementById("typing-a2");
      nestedItem.focus();
      expect(tab()).toEqual(true);
      expect(document.activeElement).toEqual(nestedItem);
    });

    it("uses the accordion link as the last item when it is closed", () => {
      document.getElementById("last-accordion")
        .classList.add("accordion--closed");
      const lastLink = document.getElementById("last-accordion-link");
      lastLink.focus();
      expect(tab()).toEqual(false);
      expect(document.activeElement).toEqual(
        document.querySelector(".filter-panel__close"));
    });

    it("closes the panel on escape", () => {
      const closeButton = document.querySelector(".filter-panel__close");
      const clickSpy = jest.spyOn(closeButton, "click");
      keydown(27);
      keyup(27);
      expect(clickSpy).toHaveBeenCalled();
    });
  });
});
