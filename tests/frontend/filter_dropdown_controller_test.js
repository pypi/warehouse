/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, afterEach, describe, it */

import { Application } from "@hotwired/stimulus";
import FilterDropdownController from "../../warehouse/static/js/warehouse/controllers/filter_dropdown_controller";
import { delay } from "./utils";

const dropdownHTML = `
<div data-controller="filter-dropdown">
  <button type="button" aria-haspopup="true" aria-expanded="false"
      data-filter-dropdown-target="trigger" data-action="filter-dropdown#toggle">Filter</button>
  <div aria-hidden="true" data-filter-dropdown-target="content">
    <input type="radio" name="g" value="a" data-action="filter-dropdown#close">
  </div>
</div>
`;

describe("Filter dropdown controller", () => {
  let application;

  beforeEach(async () => {
    document.body.innerHTML = dropdownHTML;

    application = Application.start();
    application.register("filter-dropdown", FilterDropdownController);
    await delay(30);
  });

  afterEach(() => {
    application.stop();
  });

  it("starts closed", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(content).toHaveAttribute("aria-hidden", "true");
    expect(content).not.toHaveClass("display-block");
  });

  it("opens when the trigger is clicked", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");

    trigger.click();

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(content).not.toHaveAttribute("aria-hidden");
    expect(content).toHaveClass("display-block");
  });

  it("closes when the trigger is clicked again", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");

    trigger.click();
    trigger.click();

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(content).toHaveAttribute("aria-hidden", "true");
    expect(content).not.toHaveClass("display-block");
  });

  it("closes when a radio inside it is selected", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");
    const radio = document.querySelector("input[type='radio']");

    trigger.click();
    expect(content).toHaveClass("display-block");

    radio.click();

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(content).toHaveAttribute("aria-hidden", "true");
    expect(content).not.toHaveClass("display-block");
  });

  it("does not close on mouseleave", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");

    trigger.click();
    content.dispatchEvent(new MouseEvent("mouseout", { bubbles: true }));
    document.querySelector("[data-controller='filter-dropdown']").dispatchEvent(new MouseEvent("mouseout", { bubbles: true }));

    expect(content).toHaveClass("display-block");
  });
});
