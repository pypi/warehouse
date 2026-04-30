/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, describe, it */

import { Application } from "@hotwired/stimulus";
import InstallerCommandController from "../../warehouse/static/js/warehouse/controllers/installer_command_controller";

function mount({ name = "django", spec = "", index = "", quote = "false" } = {}) {
  document.body.innerHTML = `
    <div data-controller="installer-command"
         data-installer-command-name-value="${name}"
         data-installer-command-spec-value="${spec}"
         data-installer-command-index-value="${index}"
         data-installer-command-quote-value="${quote}">
      <select data-installer-command-target="select"
              data-action="change->installer-command#change">
        <option value="pip">pip</option>
        <option value="uv">uv</option>
        <option value="poetry">poetry</option>
        <option value="pdm">pdm</option>
        <option value="pipenv">pipenv</option>
      </select>
      <span data-installer-command-target="command">placeholder</span>
      <span data-installer-command-target="full">placeholder</span>
    </div>
  `;
  const application = Application.start();
  application.register("installer-command", InstallerCommandController);
  return {
    select: document.querySelector("select"),
    command: document.querySelector("[data-installer-command-target='command']"),
    full: document.querySelector("[data-installer-command-target='full']"),
  };
}

function clearInstallerCookie() {
  document.cookie = "pypi-installer=; max-age=0; path=/";
}

describe("InstallerCommandController", () => {
  beforeEach(() => {
    clearInstallerCookie();
  });

  it("renders pip suffix and full command by default", async () => {
    const { command, full } = mount();
    await Promise.resolve();
    expect(command.textContent).toBe("install django");
    expect(full.textContent).toBe("pip install django");
  });

  it("on change writes cookie, updates suffix and full command", async () => {
    const { select, command, full } = mount();
    await Promise.resolve();
    select.value = "uv";
    select.dispatchEvent(new Event("change"));
    expect(command.textContent).toBe("pip install django");
    expect(full.textContent).toBe("uv pip install django");
    expect(document.cookie).toContain("pypi-installer=uv");
  });

  it("hydrates the select from the cookie on connect", async () => {
    document.cookie = "pypi-installer=poetry; path=/";
    const { select, command, full } = mount({ spec: "==5.0" });
    await Promise.resolve();
    expect(select.value).toBe("poetry");
    expect(command.textContent).toBe("add django==5.0");
    expect(full.textContent).toBe("poetry add django==5.0");
  });

  it("includes the test-PyPI index flag for pip-family installers", async () => {
    const { select, command, full } = mount({
      index: " -i https://test.pypi.org/simple/",
    });
    await Promise.resolve();
    expect(command.textContent).toBe("install -i https://test.pypi.org/simple/ django");
    expect(full.textContent).toBe("pip install -i https://test.pypi.org/simple/ django");
    select.value = "uv";
    select.dispatchEvent(new Event("change"));
    expect(command.textContent).toBe("pip install -i https://test.pypi.org/simple/ django");
    expect(full.textContent).toBe("uv pip install -i https://test.pypi.org/simple/ django");
  });

  it("quotes the spec when the version has an epoch", async () => {
    const { command, full } = mount({ spec: "==1!2.0", quote: "true" });
    await Promise.resolve();
    expect(command.textContent).toBe("install 'django==1!2.0'");
    expect(full.textContent).toBe("pip install 'django==1!2.0'");
  });

  it("ignores an unknown cookie value and falls back to pip", async () => {
    document.cookie = "pypi-installer=bogus; path=/";
    const { select, command, full } = mount();
    await Promise.resolve();
    expect(select.value).toBe("pip");
    expect(command.textContent).toBe("install django");
    expect(full.textContent).toBe("pip install django");
  });

  it("renders without errors when only one of command/full is present", async () => {
    document.body.innerHTML = `
      <div data-controller="installer-command"
           data-installer-command-name-value="django"
           data-installer-command-spec-value=""
           data-installer-command-index-value=""
           data-installer-command-quote-value="false">
        <select data-installer-command-target="select"
                data-action="change->installer-command#change">
          <option value="pip">pip</option>
          <option value="uv">uv</option>
        </select>
        <code data-installer-command-target="full">placeholder</code>
      </div>
    `;
    const application = Application.start();
    application.register("installer-command", InstallerCommandController);
    await Promise.resolve();
    const code = document.querySelector("code");
    expect(code.textContent).toBe("pip install django");
  });
});
