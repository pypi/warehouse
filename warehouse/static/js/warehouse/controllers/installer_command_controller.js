/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";

// Each entry returns the command tail (everything AFTER the installer
// name). The select itself shows the installer name, so the visible UI
// reads as "<select-value> <suffix>" with no duplication. ${i} is the
// test-PyPI "-i URL" flag (or "") for tools that accept it.
const SUFFIX = {
  pip:    (s, i) => `install${i} ${s}`,
  uv:     (s, i) => `pip install${i} ${s}`,
  poetry: (s) => `add ${s}`,
  pdm:    (s) => `add ${s}`,
  pipenv: (s) => `install ${s}`,
};

const COOKIE = "pypi-installer";
const FALLBACK = "pip";
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

function readCookie(name) {
  const m = document.cookie.match(
    new RegExp("(?:^|;\\s*)" + name + "=([^;]+)"),
  );
  return m ? decodeURIComponent(m[1]) : null;
}

function writeCookie(name, value) {
  document.cookie =
    `${name}=${encodeURIComponent(value)}` +
    `; max-age=${COOKIE_MAX_AGE}; path=/; SameSite=Lax`;
}

export default class extends Controller {
  static targets = ["select", "command", "full"];
  static values = {
    name:  String,
    spec:  String,
    index: String,
    quote: Boolean,
  };

  connect() {
    const saved = readCookie(COOKIE);
    if (saved && saved in SUFFIX) {
      this.selectTarget.value = saved;
    }
    this.render();
  }

  change() {
    writeCookie(COOKIE, this.selectTarget.value);
    this.render();
  }

  render() {
    const installer = this.selectTarget.value;
    const tmpl = SUFFIX[installer] || SUFFIX[FALLBACK];
    const spec = `${this.nameValue}${this.specValue}`;
    const quoted = this.quoteValue ? `'${spec}'` : spec;
    const suffix = tmpl(quoted, this.indexValue);
    if (this.hasCommandTarget) this.commandTarget.textContent = suffix;
    if (this.hasFullTarget) this.fullTarget.textContent = `${installer} ${suffix}`;
  }
}
