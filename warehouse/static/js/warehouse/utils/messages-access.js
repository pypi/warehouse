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

const i18n = require("gettext.js/dist/gettext.cjs.js");

/**
 * Get the translation using num to choose the appropriate string.
 *
 * When importing this function, it must be named in a particular way to be recognised by babel
 * and have the translation strings extracted correctly.
 * Function 'ngettext' for plural extraction.
 *
 * Any placeholders must be specified as
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
 * @param extras {string} Additional values to put in placeholders.
 * @returns {string} The translated text.
 * @see https://www.gnu.org/software/gettext/manual/gettext.html#Language-specific-options
 * @see https://docs.pylonsproject.org/projects/pyramid/en/latest/api/i18n.html#pyramid.i18n.Localizer.pluralize
 */
export function ngettext(singular, plural, num, ...extras) {
  const singularIsString = typeof singular === "string" || singular instanceof String;
  if(singularIsString) {
    // construct the translation using the fallback language (english)
    i18n.setMessages("messages", "en", {[singular]:[singular, plural]}, "nplurals = 2; plural = (n != 1)");
  } else {
    // After the webpack localizer processing,
    // the non-string 'singular' is the translation data.
    i18n.loadJSON(singular.data, "messages");
  }

  return i18n.ngettext(singular.singular, plural, num, ...extras);
}

/**
 * Get the singular translation.
 *
 * When importing this function, it must be named in a particular way to be recognised by babel
 * and have the translation strings extracted correctly.
 * Function 'gettext' for singular extraction.
 *
 * Any placeholders must be specified as
 *
 * @param singular {string} The default string for the singular translation.
 * @param extras {string} Additional values to put in placeholders.
 * @returns {string} The translated text.
 */
export function gettext(singular, ...extras) {
  const singularIsString = typeof singular === "string" || singular instanceof String;
  if(singularIsString) {
    // construct the translation using the fallback language (english)
    i18n.setMessages("messages", "en", {[singular]:[singular]}, "nplurals = 2; plural = (n != 1)");
  } else {
    // After the webpack localizer processing,
    // the non-string 'singular' is the translation data.
    i18n.loadJSON(singular.data, "messages");
  }

  return i18n.gettext(singular.singular,  ...extras);
}
