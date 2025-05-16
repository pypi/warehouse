/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import ChangeRoleController from "../../warehouse/static/js/warehouse/controllers/change_role_controller";

const roleContent = `
  <div data-controller="change-role" data-change-role-current-value="Maintainer">
    <form class="table__change-role" method="POST" action="/manage/project/pytest-socket/collaboration/change/">
      <select id="role-for-deadbeef" class="table__change-field" name="role_name" data-action="change-role#change" autocomplete="off">
        <option value="Maintainer" selected="">
          Maintainer
        </option>
        <option value="Owner">
          Owner
        </option>
      </select>
      <button class="button button--primary table__change-button" title="Save role" data-change-role-target="saveButton" style="visibility: hidden;">
        Save
      </button>
    </form>
  </div>
`;

describe("ChangeRoleController", () => {
  beforeEach(() => {
    document.body.innerHTML = roleContent;
    const application = Application.start();
    application.register("change-role", ChangeRoleController);
  });

  describe("initial state", () => {
    it("hides the button if the role is the same as the current role", () => {
      const button = document.querySelector(".table__change-button");
      expect(button.style.visibility).toEqual("hidden");
    });
  });

  describe("change selection", () => {
    it("shows the button and then hides it if changed back", () => {
      const select = document.querySelector(".table__change-field");

      select.value = "Owner";
      select.dispatchEvent(new Event("change"));

      let button = document.querySelector(".table__change-button");
      expect(button.style.visibility).toEqual("visible");

      select.value = "Maintainer";
      select.dispatchEvent(new Event("change"));

      button = document.querySelector(".table__change-button");
      expect(button.style.visibility).toEqual("hidden");
    });
  });
});
