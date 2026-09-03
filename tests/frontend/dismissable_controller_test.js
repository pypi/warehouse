/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import DismissableController from "../../warehouse/static/js/warehouse/controllers/dismissable_controller";

const calloutBlock = `
  <div id="element" class="callout-block" data-controller="dismissable" data-dismissable-identifier="settings">
    <h3>Project description and sidebar</h3>
    <button id="dismiss" type="button" title="Dismiss" data-action="click->dismissable#dismiss" class="callout-block__dismiss" aria-label="close"><i class="fa fa-times" aria-hidden="true"></i></button>
  </div>
`;

const start = () => {
  const application = Application.start();
  application.register("dismissable", DismissableController);
};

describe("Dismissable controller", () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = calloutBlock;
  });

  describe("nothing stored", function () {
    beforeEach(start);

    it("the element is not dismissed", function () {
      expect(document.getElementById("element")).not.toHaveClass("callout-block--dismissed");
    });

    it("dismissing stores the state", function () {
      document.getElementById("dismiss").click();

      expect(document.getElementById("element")).toHaveClass("callout-block--dismissed");
      expect(localStorage.getItem("callout_block_settings_dismissed")).toEqual("1");
    });
  });

  describe("stored as dismissed", function () {
    // Application.start() connects controllers asynchronously, so the store has
    // to be seeded and the application started before the assertion's tick.
    beforeEach(() => {
      localStorage.setItem("callout_block_settings_dismissed", "1");
      start();
    });

    it("the element starts dismissed", function () {
      expect(document.getElementById("element")).toHaveClass("callout-block--dismissed");
    });
  });

  describe("stored under a different identifier", function () {
    beforeEach(() => {
      localStorage.setItem("callout_block_releases_dismissed", "1");
      start();
    });

    it("the element is left alone", function () {
      expect(document.getElementById("element")).not.toHaveClass("callout-block--dismissed");
    });
  });
});
