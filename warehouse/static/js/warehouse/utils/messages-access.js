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

import i18n from "gettext.js/dist/gettext.esm";

const i18nInst = i18n();

// the value for 'messagesAccessLocaleData' is set by webpack.plugin.localize.js
var messagesAccessLocaleData = {"": {"language": "en", "plural-forms": "nplurals = 2; plural = (n != 1)"}};
i18nInst.loadJSON(messagesAccessLocaleData, "messages");

/**
 * Get the translation using num to choose the appropriate string.
 *
 * When importing this function, it must be named in a particular way to be recognised by babel
 * and have the translation strings extracted correctly.
 * Function 'ngettext' for plural extraction.
 *
 * Any placeholders must be specified as %1, %2, etc.
 *
 * @example
 * import { ngettext } from "warehouse/utils/messages-access";
 * // For a singular and plural and placeholder string:
 * ngettext("About a minute ago", "About %1 minutes ago", numMinutes, numMinutes);

 * @param singular {string} The default string for the singular translation.
 * @param plural {string} The default string for the plural translation.
 * @param num {number} The number to use to select the appropriate translation.
 * @param extras {string} Additional values to put in placeholders.
 * @returns {string} The translated text.
 * @see https://github.com/guillaumepotier/gettext.js
 * @see https://www.gnu.org/software/gettext/manual/gettext.html#Language-specific-options
 * @see https://docs.pylonsproject.org/projects/pyramid/en/latest/api/i18n.html#pyramid.i18n.Localizer.pluralize
 */
export function ngettext(singular, plural, num, ...extras) {
  return i18nInst.ngettext(singular, plural, num, ...extras);
}

/**
 * Get the singular translation.
 *
 * When importing this function, it must be named in a particular way to be recognised by babel
 * and have the translation strings extracted correctly.
 * Function 'gettext' for singular extraction.
 *
 * Any placeholders must be specified as %1, %2, etc.
 *
 * @example
 * import { gettext } from "warehouse/utils/messages-access";
 * // For a singular only string:
 * gettext("Just now");
 *
 * @param singular {string} The default string for the singular translation.
 * @param extras {string} Additional values to put in placeholders.
 * @returns {string} The translated text.
 */
export function gettext(singular, ...extras) {
  return i18nInst.gettext(singular, ...extras);
}
