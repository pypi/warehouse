/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, afterEach, describe, it, jest */

import { Application } from "@hotwired/stimulus";

// The project page renders the placement twice (desktop sidebar and mobile
// "Metadata" tab), so the fixture does too.
const placement = `
  <div class="sidebar-section"
       data-controller="sponsor"
       data-sponsor-placement-value="pypi-sidebar">
    <div data-sponsor-target="item" data-sponsor-slug="alpha" hidden>
      <a href="#alpha" data-action="sponsor#click">Alpha</a>
    </div>
    <div data-sponsor-target="item" data-sponsor-slug="bravo" hidden>
      <a href="#bravo" data-action="sponsor#click">Bravo</a>
    </div>
  </div>
`;

const props = { sponsor: "bravo", placement: "pypi-sidebar" };

let application;
let observerCallbacks;

// The controller keeps page-level state at module level, so every test gets a
// fresh copy of the module.
async function startStimulus() {
  document.body.innerHTML = placement + placement;
  await jest.isolateModulesAsync(async () => {
    const SponsorController = (
      await import("../../warehouse/static/js/warehouse/controllers/sponsor_controller")
    ).default;
    application = new Application();
    application.register("sponsor", SponsorController);
    await application.start();
  });
}

function reportVisibility(intersectionRatio) {
  observerCallbacks.forEach((callback) => callback([{ intersectionRatio }]));
}

function visibleItems() {
  return Array.from(document.querySelectorAll("[data-sponsor-target='item']"))
    .filter((item) => !item.hidden)
    .map((item) => item.dataset.sponsorSlug);
}

describe("SponsorController", () => {
  beforeEach(() => {
    window.plausible = jest.fn();
    jest.spyOn(Math, "random").mockReturnValue(0.99);
    observerCallbacks = [];
    window.IntersectionObserver = jest.fn((callback) => {
      observerCallbacks.push(callback);
      return { observe: jest.fn(), disconnect: jest.fn() };
    });
  });

  afterEach(() => {
    // Otherwise the previous test's application reconnects its own copy of
    // the controller module to the next test's DOM.
    application.stop();
    jest.restoreAllMocks();
    delete window.IntersectionObserver;
  });

  it("reveals the same sponsor in every copy of the placement", async () => {
    await startStimulus();

    expect(visibleItems()).toEqual(["bravo", "bravo"]);
  });

  it("reports one impression per page once the placement is half visible", async () => {
    await startStimulus();

    reportVisibility(0.6);
    reportVisibility(0.6);

    expect(window.plausible).toHaveBeenCalledTimes(1);
    expect(window.plausible).toHaveBeenCalledWith("Sponsor Impression", {
      props,
      interactive: false,
    });
  });

  it("does not report an impression below half visibility", async () => {
    await startStimulus();

    reportVisibility(0.4);

    expect(window.plausible).not.toHaveBeenCalled();
  });

  it("reports clicks on the sponsor link", async () => {
    await startStimulus();

    document.querySelector("a[href='#bravo']").click();

    expect(window.plausible).toHaveBeenCalledWith("Sponsor Click", { props });
  });

  it("works without IntersectionObserver and without analytics", async () => {
    delete window.IntersectionObserver;
    delete window.plausible;
    await startStimulus();

    document.querySelector("a[href='#bravo']").click();

    expect(visibleItems()).toEqual(["bravo", "bravo"]);
  });
});
