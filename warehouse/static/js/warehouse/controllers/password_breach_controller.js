/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";
import { debounce } from "debounce";
import { gettext } from "../utils/messages-access";

export default class extends Controller {
  static targets = ["password", "message"];

  connect() {
    this.check = debounce(this.check, 1000);
    this._lastCheckedPassword = null;
  }

  check() {
    if (this.passwordTarget.value !== this._lastCheckedPassword) {
      this.hideMessage();
      if (this.passwordTarget.value.length > 2) {
        this._lastCheckedPassword = this.passwordTarget.value;
        return this.checkPassword(this.passwordTarget.value).catch(
          e => {
            console.error(e);  // eslint-disable-line no-console
            this.hideMessage();  // default to hiding the message on errors
          },
        );
      }
    }
    return null;
  }

  async checkPassword(password) {
    let digest = await this.digestMessage(password);
    let hex = this.hexString(digest);
    let response = await fetch(this.getURL(hex));
    if (response.ok === false) {
      const msgText = gettext("Error while validating hashed password, disregard on development");
      console.error(`${msgText}: ${response.status} ${response.statusText}`);  // eslint-disable-line no-console
    } else {
      let text = await response.text();
      this.parseResponse(text, hex);
    }
  }

  async digestMessage(message) {
    // https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
    const encoder = new TextEncoder();
    const data = encoder.encode(message);
    return window.crypto.subtle.digest("SHA-1", data);
  }

  hexString(buffer) {
    const byteArray = new Uint8Array(buffer);

    const hexCodes = [...byteArray].map(value => {
      const hexCode = value.toString(16);
      const paddedHexCode = hexCode.padStart(2, "0");
      return paddedHexCode;
    });

    return hexCodes.join("");
  }

  getURL(hashedPassword) {
    // note the HIBP API needs to be included in the Content Security Policy
    return `https://api.pwnedpasswords.com/range/${hashedPassword.slice(0, 5)}`;
  }

  parseResponse(responseText, hashedPassword) {
    // The dataset that comes back from HIBP looks like:
    //
    // 0018A45C4D1DEF81644B54AB7F969B88D65:1
    // 00D4F6E8FA6EECAD2A3AA415EEC418D38EC:2
    // 011053FD0102E94D6AE2F8B83D76FAF94F6:1
    // 012A7CA357541F0AC487871FEEC1891C49C:2
    // 0136E006E24E7D152139815FB0FC6A50B15:2
    // ...
    //
    // That is, it is a line delimited textual data, where each line is a hash, a
    // colon, and then the number of times that password has appeared in a breach.
    // For our uses, we're going to consider any password that has ever appeared in
    // a breach to be insecure, even if only once.
    let isBreached = responseText.split("\n").some(
      line => line.toLowerCase().split(":")[0] === hashedPassword.slice(5),
    );
    if (isBreached) {
      this.showMessage();
    } else {
      this.hideMessage();
    }
  }

  showMessage() {
    this.messageTarget.classList.remove("hidden");
  }

  hideMessage() {
    this.messageTarget.classList.add("hidden");
  }
}
