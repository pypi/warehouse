/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import AttestationsViewerController from "../../warehouse/static/js/warehouse/controllers/attestations_viewer_controller";

const viewerHTML = `
<div class="attestations-viewer" data-controller="attestations-viewer">
  <ul class="attestations-viewer__file-list">
    <li class="attestations-viewer__file-item attestations-viewer__file-item--is-selected" data-attestations-viewer-target="item" data-filename="sample-1.0.tar.gz">
      <button type="button" data-action="attestations-viewer#select" aria-pressed="true">sample-1.0.tar.gz</button>
    </li>
    <li class="attestations-viewer__file-item" data-attestations-viewer-target="item" data-filename="sample-1.0-py3-none-any.whl">
      <button type="button" data-action="attestations-viewer#select" aria-pressed="false">sample-1.0-py3-none-any.whl</button>
    </li>
  </ul>
  <div class="attestations-viewer__content">
    <div data-attestations-viewer-target="content" data-filename="sample-1.0.tar.gz">
      <h3>Attestation for sample-1.0.tar.gz</h3>
      <code class="attestation__checksum" data-controller="clipboard">abc123</code>
    </div>
    <div class="hidden" data-attestations-viewer-target="content" data-filename="sample-1.0-py3-none-any.whl">
      <h3>Attestation for sample-1.0-py3-none-any.whl</h3>
      <code class="attestation__checksum">def456</code>
    </div>
  </div>
</div>
`;

describe("Attestations viewer controller", () => {
  beforeEach(() => {
    document.body.innerHTML = viewerHTML;

    const application = Application.start();
    application.register("attestations-viewer", AttestationsViewerController);
  });

  describe("on initialization", () => {
    it("shows the first file as selected and its content panel visible", () => {
      const items = document.querySelectorAll("[data-attestations-viewer-target='item']");
      const contents = document.querySelectorAll("[data-attestations-viewer-target='content']");

      expect(items[0]).toHaveClass("attestations-viewer__file-item--is-selected");
      expect(items[0].querySelector("button")).toHaveAttribute("aria-pressed", "true");
      expect(contents[0]).not.toHaveClass("hidden");

      expect(items[1]).not.toHaveClass("attestations-viewer__file-item--is-selected");
      expect(items[1].querySelector("button")).toHaveAttribute("aria-pressed", "false");
      expect(contents[1]).toHaveClass("hidden");
    });

    it("only the visible panel's checksum has a live clipboard controller", () => {
      const contents = document.querySelectorAll("[data-attestations-viewer-target='content']");

      expect(contents[0].querySelector(".attestation__checksum")).toHaveAttribute("data-controller", "clipboard");
      expect(contents[1].querySelector(".attestation__checksum")).not.toHaveAttribute("data-controller");
    });
  });

  describe("on select", () => {
    it("shows the content panel for the file whose button was clicked", () => {
      const items = document.querySelectorAll("[data-attestations-viewer-target='item']");
      items[1].querySelector("button").click();

      expect(items[0]).not.toHaveClass("attestations-viewer__file-item--is-selected");
      expect(items[0].querySelector("button")).toHaveAttribute("aria-pressed", "false");
      expect(items[1]).toHaveClass("attestations-viewer__file-item--is-selected");
      expect(items[1].querySelector("button")).toHaveAttribute("aria-pressed", "true");

      const contents = document.querySelectorAll("[data-attestations-viewer-target='content']");
      expect(contents[0]).toHaveClass("hidden");
      expect(contents[1]).not.toHaveClass("hidden");
    });

    it("switches back when a different file's button is clicked", () => {
      const items = document.querySelectorAll("[data-attestations-viewer-target='item']");
      items[1].querySelector("button").click();
      items[0].querySelector("button").click();

      expect(items[0]).toHaveClass("attestations-viewer__file-item--is-selected");
      expect(items[1]).not.toHaveClass("attestations-viewer__file-item--is-selected");

      const contents = document.querySelectorAll("[data-attestations-viewer-target='content']");
      expect(contents[0]).not.toHaveClass("hidden");
      expect(contents[1]).toHaveClass("hidden");
    });

    it("moves the clipboard controller to the newly selected panel's checksum", () => {
      const items = document.querySelectorAll("[data-attestations-viewer-target='item']");
      items[1].querySelector("button").click();

      const contents = document.querySelectorAll("[data-attestations-viewer-target='content']");
      expect(contents[0].querySelector(".attestation__checksum")).not.toHaveAttribute("data-controller");
      expect(contents[1].querySelector(".attestation__checksum")).toHaveAttribute("data-controller", "clipboard");
    });
  });
});
