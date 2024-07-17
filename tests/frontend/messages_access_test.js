/* Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/* global expect, describe, it */

import {gettext, ngettext, ngettextCustom} from "../../warehouse/static/js/warehouse/utils/messages-access";


describe("messages access util", () => {

  describe("gettext with defaults", () => {
    it("uses default singular when no translation is available", async () => {
      const singular = "My default message.";
      const result = gettext(singular);
      expect(result).toEqual(singular);
    });
    it("inserts placeholders into the default singular", async () => {
      const singular = "My default message: %1";
      const extras = ["more message here"];
      const result = gettext(singular, ...extras);
      expect(result).toEqual("My default message: more message here");
    });
  });

  describe("ngettext with defaults", () => {
    it("uses default singular when no translation is available", async () => {
      const singular = "My default message.";
      const plural = "My default messages.";
      const num = 1;
      const result = ngettext(singular, plural, num);
      expect(result).toEqual(singular);
    });
    it("inserts placeholders into the default singular", async () => {
      const singular = "My %2 default %1 message.";
      const plural = "My default messages.";
      const num = 1;
      const extras = ["more message here", "something else"];
      const result = ngettext(singular, plural, num, ...extras);
      expect(result).toEqual("My something else default more message here message.");
    });
    it("uses default plural when no translation is available", async () => {
      const singular = "My default message.";
      const plural = "My default messages.";
      const num = 2;
      const result = ngettext(singular, plural, num);
      expect(result).toEqual(plural);
    });
    it("inserts placeholders into the default plural", async () => {
      const singular = "My %2 default %1 message.";
      const plural = "My default plural messages %1 %2.";
      const num = 2;
      const extras = ["more message here", "something else"];
      const result = ngettext(singular, plural, num, ...extras);
      expect(result).toEqual("My default plural messages more message here something else.");
    });
  });

  describe("with translation data", () => {
    const data = {
      "": {"language": "fr", "plural-forms": "nplurals=2; plural=n > 1;"},
      "My default message.": "My translated message.",
      "My %2 message with placeholders %1.": "My translated %1 message with placeholders %2",
      "My message with plurals": ["My translated message 1.", "My translated messages 2."],
      "My message with plurals %1 again": ["My translated message 1 %1.", "My translated message 2 %1"],
    };
    const pluralForms = function (n) {
      let nplurals, plural;
      nplurals = 2; plural = n > 1;
      return {total: nplurals, index: ((nplurals > 1 && plural === true) ? 1 : (plural ? plural : 0))};
    };
    it("uses singular when translation is available", async () => {
      const singular = "My default message.";
      const result = ngettextCustom(singular, null, 1, [], data, pluralForms);
      expect(result).toEqual("My translated message.");
    });
    it("inserts placeholders into the singular translation", async () => {
      const singular = "My %2 message with placeholders %1.";
      const extras = ["more message here", "another"];
      const result = ngettextCustom(singular, null, 1, extras, data, pluralForms);
      expect(result).toEqual("My translated more message here message with placeholders another");
    });
    it("uses plural when translation is available", async () => {
      const singular = "My message with plurals";
      const plural = "My messages with plurals";
      const num = 2;
      const extras = ["not used"];
      const result = ngettextCustom(singular, plural, num, extras, data, pluralForms);
      expect(result).toEqual("My translated messages 2.");
    });
    it("inserts placeholders into the plural translation", async () => {
      const singular = "My message with plurals %1 again";
      const plural = "My messages with plurals %1 again";
      const num = 2;
      const extras = ["more message here"];
      const result = ngettextCustom(singular, plural, num, extras, data, pluralForms);
      expect(result).toEqual("My translated message 2 more message here");
    });
  });
});
