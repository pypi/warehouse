/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

// PSF sponsor logo placement in the project and organization sidebars.
//
// The server renders every eligible sponsor hidden, because the page is
// cached at the CDN for a day. This controller reveals one at random, then
// reports a viewable impression and clicks to analytics.python.org.
//
// The project page renders the placement twice (desktop sidebar and the
// mobile "Metadata" tab), so the choice and the impression are kept at module
// level: both copies show the same sponsor and a page view counts once.
let chosenIndex = null;
let impressionReported = false;

export default class extends Controller {
  static targets = ["item"];
  static values = { placement: String };

  connect() {
    if (chosenIndex === null) {
      chosenIndex = Math.floor(Math.random() * this.itemTargets.length);
    }
    this.itemTargets.forEach((item, index) => {
      item.hidden = index !== chosenIndex;
    });
    this.sponsor = this.itemTargets[chosenIndex].dataset.sponsorSlug;

    if (!("IntersectionObserver" in window)) {
      return;
    }
    this.observer = new IntersectionObserver(
      (entries) => {
        if (impressionReported || !entries.some((entry) => entry.intersectionRatio >= 0.5)) {
          return;
        }
        impressionReported = true;
        this.observer.disconnect();
        this.track("Sponsor Impression", { interactive: false });
      },
      { threshold: 0.5 },
    );
    this.observer.observe(this.element);
  }

  disconnect() {
    if (this.observer) {
      this.observer.disconnect();
    }
  }

  click() {
    this.track("Sponsor Click");
  }

  track(event, options = {}) {
    if (!window.plausible) {
      return;
    }
    window.plausible(event, {
      props: { sponsor: this.sponsor, placement: this.placementValue },
      ...options,
    });
  }
}
