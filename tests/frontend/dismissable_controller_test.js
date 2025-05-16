/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import DismissableController from "../../warehouse/static/js/warehouse/controllers/dismissable_controller";

describe("Dismissable controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
  <div id="element" class="callout-block" data-controller="dismissable" data-dismissable-identifier="settings">
    <h3>Project description and sidebar</h3>
    <p>
      To set the 'warehouse' description, author, links,
      classifiers, and other details for your next release, use
      the <a href="https://packaging.python.org/guides/distributing-packages-using-setuptools/#setup-args" rel="noopener" target="_blank"><code>setup()</code>
      arguments in your <code>setup.py</code> file</a>. Updating these
      fields will not change the metadata for past
      releases. Additionally, you <strong>must</strong> use
      <a href="https://twine.readthedocs.io/" rel="noopener" target="_blank">Twine</a>
      to upload your files in order to get full support for these fields. See
      <a href="https://packaging.python.org/guides/distributing-packages-using-setuptools/" rel="noopener" target="_blank">the Python Packaging User Guide</a> for more help.
    </p>
    <button id="dismiss" type="button" title="Dismiss" data-action="click->dismissable#dismiss" class="callout-block__dismiss" aria-label="close"><i class="fa fa-times" aria-hidden="true"></i></button>
  </div>
    `;

    const application = Application.start();
    application.register("dismissable", DismissableController);
  });

  describe("no cookie is present", function () {
    it("the element is not dismissed", function () {
      const el = document.getElementById("element");
      expect(el).not.toHaveClass("callout-block--dismissed");
    });

    it("the element is dismissable", function () {
      const btn = document.getElementById("dismiss");
      btn.click();

      const el = document.getElementById("element");
      expect(el).toHaveClass("callout-block--dismissed");
      expect(document.cookie).toContain("callout_block_settings_dismissed=1");
    });
  });

  describe("cookie is present", function () {
    it("the element is dismissed and not dismissable", function () {
      document.cookie = "callout_block_settings_dismissed=1";
      const application = Application.start();
      application.register("dismissable", DismissableController);

      const el = document.getElementById("element");
      expect(el).toHaveClass("callout-block--dismissed");
    });
  });
});
