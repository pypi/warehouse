/* SPDX-License-Identifier: Apache-2.0 */

import { Controller } from "@hotwired/stimulus";
import { gettext } from "../utils/messages-access";

let zxcvbnLoadPromise = null;

function loadZxcvbn() {
  if (!zxcvbnLoadPromise) {
    zxcvbnLoadPromise = Promise.all([
      import(/* webpackChunkName: "zxcvbn-core" */ "@zxcvbn-ts/core"),
      import(/* webpackChunkName: "zxcvbn-common" */ "@zxcvbn-ts/language-common"),
      import(/* webpackChunkName: "zxcvbn-en" */ "@zxcvbn-ts/language-en"),
    ]).then(([core, common, en]) => {
      core.zxcvbnOptions.setOptions({
        graphs: common.adjacencyGraphs,
        dictionary: {
          ...common.dictionary,
          ...en.dictionary,
        },
        translations: en.translations,
      });
      return core.zxcvbn;
    });
  }
  return zxcvbnLoadPromise;
}

export default class extends Controller {
  static targets = ["password", "strengthGauge"];

  connect() {
    loadZxcvbn();
  }

  async checkPasswordStrength() {
    let password = this.passwordTarget.value;
    if (password === "") {
      this.strengthGaugeTarget.setAttribute("class", "password-strength__gauge");
      this.setScreenReaderMessage(gettext("Password field is empty"));
    } else {
      const zxcvbn = await loadZxcvbn();
      let zxcvbnResult = zxcvbn(password.substring(0, 100));
      this.strengthGaugeTarget.setAttribute("class", `password-strength__gauge password-strength__gauge--${zxcvbnResult.score}`);
      this.strengthGaugeTarget.setAttribute("data-zxcvbn-score", zxcvbnResult.score);

      const feedbackSuggestions = zxcvbnResult.feedback.suggestions.join(" ");
      if (feedbackSuggestions) {
        // Note: we can't localize this string because it will be mixed
        // with other non-localizable strings from zxcvbn
        this.setScreenReaderMessage("Password is too easily guessed. " + feedbackSuggestions);
      } else {
        this.setScreenReaderMessage(gettext("Password is strong"));
      }
    }
  }

  setScreenReaderMessage(msg) {
    this.strengthGaugeTarget.querySelector(".sr-only").textContent = msg;
  }
}
