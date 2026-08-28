/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import CollapsibleController from "../../warehouse/static/js/warehouse/controllers/collapsible_controller";

const calloutBlock = `
  <details id="element" class="callout-block" data-controller="collapsible" data-collapsible-identifier="project_roles" open>
    <summary id="collapse" class="callout-block__heading" data-action="click->collapsible#save">Project Roles</summary>
  </details>
`;

const start = () => {
  const application = Application.start();
  application.register("collapsible", CollapsibleController);
};

describe("Collapsible controller", () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = calloutBlock;
  });

  describe("nothing stored", function () {
    beforeEach(start);

    it("the element keeps the state it was rendered with", function () {
      expect(document.getElementById("element")).toHaveAttribute("open");
    });

    it("collapsing stores the state", function (done) {
      document.getElementById("collapse").click();
      document.getElementById("element").removeAttribute("open");

      // `save` defers to a macrotask so it observes the state the browser
      // settles on after the summary click, so the assertion has to as well.
      setTimeout(() => {
        expect(localStorage.getItem("callout_block_project_roles_collapsed")).toEqual("1");
        done();
      }, 0);
    });
  });

  describe("stored as collapsed", function () {
    // Application.start() connects controllers asynchronously, so the store has
    // to be seeded and the application started before the assertion's tick.
    beforeEach(() => {
      localStorage.setItem("callout_block_project_roles_collapsed", "1");
      start();
    });

    it("the element starts collapsed", function () {
      expect(document.getElementById("element")).not.toHaveAttribute("open");
    });
  });

  describe("stored as expanded", function () {
    // Application.start() connects controllers asynchronously, so the store has
    // to be seeded and the application started before the assertion's tick.
    beforeEach(() => {
      localStorage.setItem("callout_block_project_roles_collapsed", "0");
      start();
    });

    it("the element starts expanded", function () {
      expect(document.getElementById("element")).toHaveAttribute("open");
    });
  });

  describe("stored under a different identifier", function () {
    beforeEach(() => {
      localStorage.setItem("callout_block_organization_roles_collapsed", "1");
      start();
    });

    it("the element is left alone", function () {
      expect(document.getElementById("element")).toHaveAttribute("open");
    });
  });
});
