/* SPDX-License-Identifier: Apache-2.0 */

/* global expect, beforeEach, afterEach, describe, it */

import { Application } from "@hotwired/stimulus";
import InstallerCommandController from "../../warehouse/static/js/warehouse/controllers/installer_command_controller";

let application;

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
        <option value="name">Project name</option>
      </select>
      <span data-installer-command-target="command">placeholder</span>
      <span data-installer-command-target="full">placeholder</span>
      <p hidden data-installer-command-target="poetryNote">note</p>
    </div>
  `;
  application = Application.start();
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

  afterEach(() => {
    application.stop();
    document.body.innerHTML = "";
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
    expect(command.textContent).toBe("add django");
    expect(full.textContent).toBe("uv add django");
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

  it("formats per-installer testpypi flags from the URL", async () => {
    const { select, full } = mount({
      index: "https://test.pypi.org/simple/",
    });
    await Promise.resolve();
    expect(full.textContent).toBe("pip install -i https://test.pypi.org/simple/ django");
    select.value = "uv";
    select.dispatchEvent(new Event("change"));
    expect(full.textContent).toBe("uv add --index https://test.pypi.org/simple/ django");
    select.value = "pdm";
    select.dispatchEvent(new Event("change"));
    expect(full.textContent).toBe("pdm add --index-url https://test.pypi.org/simple/ django");
    select.value = "pipenv";
    select.dispatchEvent(new Event("change"));
    expect(full.textContent).toBe("pipenv install -i https://test.pypi.org/simple/ django");
    select.value = "poetry";
    select.dispatchEvent(new Event("change"));
    expect(full.textContent).toBe("poetry add --source testpypi django");
  });

  it("quotes the spec when the version has an epoch", async () => {
    const { command, full } = mount({ spec: "==1!2.0", quote: "true" });
    await Promise.resolve();
    expect(command.textContent).toBe("install 'django==1!2.0'");
    expect(full.textContent).toBe("pip install 'django==1!2.0'");
  });

  it("toggles the poetry note based on selected installer", async () => {
    const { select } = mount({ index: "https://test.pypi.org/simple/" });
    await Promise.resolve();
    const note = document.querySelector("[data-installer-command-target='poetryNote']");
    expect(note.hidden).toBe(true);
    select.value = "poetry";
    select.dispatchEvent(new Event("change"));
    expect(note.hidden).toBe(false);
    select.value = "pip";
    select.dispatchEvent(new Event("change"));
    expect(note.hidden).toBe(true);
  });

  it("ignores an unknown cookie value and falls back to pip", async () => {
    document.cookie = "pypi-installer=bogus; path=/";
    const { select, command, full } = mount();
    await Promise.resolve();
    expect(select.value).toBe("pip");
    expect(command.textContent).toBe("install django");
    expect(full.textContent).toBe("pip install django");
  });

  it("copies only the name on an epoch release from TestPyPI and restores the command", async () => {
    const { select, command, full } = mount({
      spec: "==1!2.0", quote: "true", index: "https://test.pypi.org/simple/",
    });
    await Promise.resolve();
    select.value = "name";
    select.dispatchEvent(new Event("change"));
    expect(command.textContent).toBe("django");
    expect(full.textContent).toBe("django");
    expect(document.querySelector("[data-installer-command-target='poetryNote']").hidden).toBe(true);
    select.value = "uv";
    select.dispatchEvent(new Event("change"));
    expect(full.textContent).toBe("uv add --index https://test.pypi.org/simple/ 'django==1!2.0'");
  });

  it("remembers name-only copying when navigating to another project", async () => {
    const first = mount();
    await Promise.resolve();
    first.select.value = "name";
    first.select.dispatchEvent(new Event("change"));
    application.stop();
    const second = mount({ name: "requests", spec: "==2.32.0" });
    await Promise.resolve();
    expect(second.select.value).toBe("name");
    expect(second.full.textContent).toBe("requests");
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
    application = Application.start();
    application.register("installer-command", InstallerCommandController);
    await Promise.resolve();
    const code = document.querySelector("code");
    expect(code.textContent).toBe("pip install django");
  });
});
