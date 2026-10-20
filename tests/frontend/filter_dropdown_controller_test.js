/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, afterEach, describe, it */

import { Application } from "@hotwired/stimulus";
import FilterDropdownController from "../../warehouse/static/js/warehouse/controllers/filter_dropdown_controller";
import { delay } from "./utils";

const dropdownHTML = `
<div data-controller="filter-dropdown" data-action="keydown->filter-dropdown#keydown focusout->filter-dropdown#focusout">
  <button type="button" aria-haspopup="true" aria-expanded="false"
      data-filter-dropdown-target="trigger" data-action="filter-dropdown#toggle">Filter</button>
  <div aria-hidden="true" data-filter-dropdown-target="content">
    <input type="radio" name="g" value="a" data-action="click->filter-dropdown#selectOption">
    <input type="radio" name="g" value="b" data-action="click->filter-dropdown#selectOption">
  </div>
</div>
<button type="button" id="outside">Outside the dropdown, e.g. the first file item</button>
`;

// el.click() (and a plain `new MouseEvent("click")`) default to detail: 0,
// same as the keyboard-synthesized clicks real browsers produce for arrow-key
// navigation or Space. Only an actual pointer click carries detail >= 1, so
// tests representing one must dispatch it explicitly.
function realClick(el) {
  el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, detail: 1 }));
}

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

  it("closes when a radio inside it is selected with a real click", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");
    const radio = document.querySelector("input[type='radio']");

    trigger.click();
    expect(content).toHaveClass("display-block");

    realClick(radio);

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

  it("hides without stealing focus when Tab moves focus out of the dropdown entirely, e.g. tabbing past the last option", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");
    const [, radioB] = document.querySelectorAll("input[type='radio']");
    const outside = document.getElementById("outside");

    trigger.click();
    radioB.focus();

    radioB.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    radioB.dispatchEvent(new FocusEvent("focusout", { bubbles: true, relatedTarget: outside }));
    outside.focus();

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(content).toHaveAttribute("aria-hidden", "true");
    expect(content).not.toHaveClass("display-block");
    expect(document.activeElement).toBe(outside);
  });

  it("stays open when Tab moves focus between elements still inside the dropdown, e.g. Shift+Tab onto the trigger", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");
    const [radioA, radioB] = document.querySelectorAll("input[type='radio']");

    trigger.click();
    radioA.focus();

    radioA.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    radioA.dispatchEvent(new FocusEvent("focusout", { bubbles: true, relatedTarget: radioB }));

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(content).toHaveClass("display-block");
  });

  it("ignores focusout entirely when it isn't caused by Tab, e.g. a mouse-driven focus change such as clicking a <label>", () => {
    // Clicking a <label> causes its own transient, synchronous blur/focus
    // shuffle while the browser resolves the click onto the label's
    // associated control, before focus ever settles there. Reacting to that
    // focusout at all - even via a relatedTarget or later activeElement
    // check - would hide the dropdown mid-click, before the label's click
    // can ever reach its input. So this is scoped to Tab-triggered focusout
    // only; a real human click's mousedown-to-mouseup gap also rules out
    // any fixed-delay deferral as a fix here.
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");
    const [radioA] = document.querySelectorAll("input[type='radio']");

    trigger.click();
    radioA.focus();

    // No preceding Tab keydown - this focusout is not Tab-driven.
    radioA.dispatchEvent(new FocusEvent("focusout", { bubbles: true, relatedTarget: document.body }));

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(content).toHaveClass("display-block");
  });

  it("doesn't let a stale Tab press affect a later, unrelated focusout, e.g. one caused by a mouse click", async () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");
    const [radioA] = document.querySelectorAll("input[type='radio']");

    trigger.click();
    radioA.focus();

    radioA.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    // Let the Tab-pressed safety net clear, as if focus never actually moved.
    await delay(0);

    radioA.dispatchEvent(new FocusEvent("focusout", { bubbles: true, relatedTarget: document.body }));

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(content).toHaveClass("display-block");
  });

  it("stays open when a radio's click is keyboard-synthesized (event.detail === 0), e.g. arrow-key navigation or Space", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");
    const radio = document.querySelector("input[type='radio']");

    trigger.click();
    radio.click(); // defaults to detail: 0, same as a real browser's arrow-key/Space click

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(content).toHaveClass("display-block");
  });

  it("returns focus to the trigger when a radio is selected with a real click", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const radio = document.querySelector("input[type='radio']");

    trigger.click();
    radio.focus();
    realClick(radio);

    expect(document.activeElement).toBe(trigger);
  });

  it("closes on Escape and returns focus to the trigger", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");
    const radio = document.querySelector("input[type='radio']");

    trigger.click();
    radio.focus();
    radio.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(content).toHaveAttribute("aria-hidden", "true");
    expect(content).not.toHaveClass("display-block");
    expect(document.activeElement).toBe(trigger);
  });

  it("closes on Escape when focus is still on the trigger, e.g. right after opening", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");

    trigger.click();
    trigger.focus();
    trigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(content).toHaveAttribute("aria-hidden", "true");
    expect(content).not.toHaveClass("display-block");
  });

  it("selects the focused radio on Enter, closes, and returns focus to the trigger", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");
    const [radioA] = document.querySelectorAll("input[type='radio']");
    let inputCount = 0;
    let changeCount = 0;
    radioA.addEventListener("input", () => inputCount++);
    radioA.addEventListener("change", () => changeCount++);

    trigger.click();
    radioA.focus();
    radioA.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));

    // Unlike Space, Enter doesn't natively check a focused radio - this is
    // handled explicitly in keydown() so tabbing to an option and pressing
    // Enter applies it, rather than just dismissing the dropdown. Both
    // `input` and `change` fire, since Stimulus's filter-list controller is
    // bound to the default action event for an <input>, which is `input`,
    // not `change`.
    expect(radioA.checked).toBe(true);
    expect(inputCount).toBe(1);
    expect(changeCount).toBe(1);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(content).toHaveAttribute("aria-hidden", "true");
    expect(content).not.toHaveClass("display-block");
    expect(document.activeElement).toBe(trigger);
  });

  it("doesn't fire a redundant input/change event on Enter when the focused radio is already checked", () => {
    const [radioA] = document.querySelectorAll("input[type='radio']");
    let inputCount = 0;
    let changeCount = 0;
    radioA.addEventListener("input", () => inputCount++);
    radioA.addEventListener("change", () => changeCount++);
    radioA.checked = true;

    document.querySelector("[data-filter-dropdown-target='trigger']").click();
    radioA.focus();
    radioA.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));

    expect(inputCount).toBe(0);
    expect(changeCount).toBe(0);
  });

  it("closes on Enter when focus is on the trigger, not a radio, without touching any option's checked state", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    const content = document.querySelector("[data-filter-dropdown-target='content']");
    const [radioA, radioB] = document.querySelectorAll("input[type='radio']");

    trigger.click();
    trigger.focus();
    trigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));

    expect(radioA.checked).toBe(false);
    expect(radioB.checked).toBe(false);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(content).not.toHaveClass("display-block");
  });

  it("does not intercept Enter on the trigger while closed, so the browser's native button activation can still open it", () => {
    const trigger = document.querySelector("[data-filter-dropdown-target='trigger']");
    trigger.focus();

    const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    trigger.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
  });

  it("prevents the default Enter behavior on close, so browsers don't then activate the trigger button and reopen the dropdown", () => {
    // jsdom doesn't re-activate the focused button on Enter like real
    // browsers do, so the reopening bug itself can't be reproduced here.
    // This asserts the one thing we can: that the keydown's default is
    // prevented, which is what stops real browsers from reopening it.
    const [radioA] = document.querySelectorAll("input[type='radio']");

    document.querySelector("[data-filter-dropdown-target='trigger']").click();
    radioA.focus();

    const event = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true });
    radioA.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
  });
});
