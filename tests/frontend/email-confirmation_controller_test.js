/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it, jest */

import { Application } from "@hotwired/stimulus";
import EmailConfirmationController from "../../warehouse/static/js/warehouse/controllers/email-confirmation_controller";
import { fireEvent } from "@testing-library/dom";

describe("Email confirmation controller", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div data-controller="email-confirmation">
        <dialog data-email-confirmation-target="dialog">
          <p>Please confirm that your email address is <strong data-email-confirmation-target="email"></strong>.</p>
          <button data-action="click->email-confirmation#confirm">Confirm</button>
          <button data-action="click->email-confirmation#close">Cancel</button>
        </dialog>
        <form data-email-confirmation-target="form">
          <input type="email" value="test@example.com">
          <input type="submit">
        </form>
      </div>
    `;

    const application = Application.start();
    application.register("email-confirmation", EmailConfirmationController);
  });

  it("shows the dialog on form submit", () => {
    const dialog = document.querySelector("dialog");
    const form = document.querySelector("form");
    const email = document.querySelector("strong");

    // The dialog is not visible by default
    expect(dialog.open).toBe(false);

    // The `showModal` method is mocked, so we can check if it was called
    dialog.showModal = jest.fn();

    // When the form is submitted
    fireEvent.submit(form);

    // The dialog should be visible and the email should be displayed
    expect(dialog.showModal).toHaveBeenCalled();
    expect(email.textContent).toBe("test@example.com");
  });

  it("submits the form when confirmed", () => {
    const dialog = document.querySelector("dialog");
    const form = document.querySelector("form");
    const confirmButton = document.querySelector("[data-action='click->email-confirmation#confirm']");

    // The `showModal` and `requestSubmit` methods are mocked, so we can check if they were called
    dialog.showModal = jest.fn();
    form.requestSubmit = jest.fn();

    // When the form is submitted and the dialog is confirmed
    fireEvent.submit(form);
    fireEvent.click(confirmButton);

    // The form should be submitted
    expect(form.requestSubmit).toHaveBeenCalled();
  });

  it("closes the dialog when canceled", () => {
    const dialog = document.querySelector("dialog");
    const form = document.querySelector("form");
    const cancelButton = document.querySelector("[data-action='click->email-confirmation#close']");

    // The dialog is not visible by default
    expect(dialog.open).toBe(false);

    // The `showModal` and `close` methods are mocked, so we can check if they were called
    dialog.showModal = jest.fn();
    dialog.close = jest.fn();

    // When the form is submitted and the dialog is canceled
    fireEvent.submit(form);
    fireEvent.click(cancelButton);

    // The dialog should be visible and then closed
    expect(dialog.showModal).toHaveBeenCalled();
    expect(dialog.close).toHaveBeenCalled();
  });

  it("does not show the dialog if already confirmed", () => {
    // this shouldn't happen in practice
    const dialog = document.querySelector("dialog");
    const form = document.querySelector("form");
    const confirmButton = document.querySelector("[data-action='click->email-confirmation#confirm']");

    dialog.showModal = jest.fn();
    form.requestSubmit = jest.fn();

    // Confirm once
    fireEvent.submit(form);
    fireEvent.click(confirmButton);

    // Reset mock
    dialog.showModal.mockClear();

    // Submit again
    fireEvent.submit(form);

    // The dialog should not be visible
    expect(dialog.showModal).not.toHaveBeenCalled();
  });
});
