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

const i18n = require("gettext.js");
const messages = require("./messages.json");

function determineLocale() {
  // check cookie
  const locale = document.cookie
    .split("; ")
    .find((row) => row.startsWith("_LOCALE_="))
    ?.split("=")[1];
  return locale ?? "en";
}

/**
 * Get the translation using num to choose the appropriate string.
 *
 * When importing this function, it must be named in a particular way to be recognised by babel
 * and have the translation strings extracted correctly.
 * Function 'gettext' for singular only extraction, function ngettext for singular and plural extraction.
 *
 * Any placeholders must be specified as '%1', '%2', etc.
 *
 * @example
 * import { gettext, ngettext } from "warehouse/utils/messages-access";
 * // For a singular only string:
 * gettext("Just now");
 * // For a singular and plural and placeholder string:
 * ngettext("About a minute ago", "About %1 minutes ago", numMinutes);

 * @param singular {string} The default string for the singular translation.
 * @param plural {string} The default string for the plural translation.
 * @param num {number} The number to use to select the appropriate translation.
 * @param values {array[string]} Additional values to fill the placeholders.
 * @returns {Promise<any | string>} The promise.
 * @see https://www.gnu.org/software/gettext/manual/gettext.html#Language-specific-options
 * @see https://docs.pylonsproject.org/projects/pyramid/en/latest/api/i18n.html#pyramid.i18n.Localizer.pluralize
 */
export function ngettext(singular, plural, num, ...values) {
  const locale = determineLocale();
  const json = messages.find((element) => element[""].language === locale);
  if (json) {
    i18n.loadJSON(json, "messages");
  }
  return Promise.resolve(i18n.ngettext(singular, plural, num, num, ...values));
}

/**
 * Get the singlar translation.
 *
 * When importing this function, it must be named in a particular way to be recognised by babel
 * and have the translation strings extracted correctly.
 * Function 'gettext' for singular only extraction, function ngettext for singular and plural extraction.
 *
 * Any placeholders must be specified as '%1', '%2', etc.
 *
 * @param singular {string} The default string for the singular translation.
 * @param values {array[string]} Additional values to fill the placeholders.
 * @returns {Promise<any | string>} The promise.
 */
export function gettext(singular, ...values) {
  return Promise.resolve(i18n.gettext(singular, ...values));
}
