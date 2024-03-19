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

const fetchOptions = {
  mode: "same-origin",
  credentials: "same-origin",
  cache: "default",
  redirect: "follow",
};

/**
 * Get the translation using num to choose the appropriate string.
 *
 * When importing this function, it must be named in a particular way to be recognised by babel
 * and have the translation strings extracted correctly.
 *
 * This approach uses the server-side localizer to process the translation strings.
 *
 * Any placeholders must be specified as '${placeholderName}' surrounded by single or double quote,
 * not backticks (template literal).
 *
 * @example
 * // Name the function 'gettext' for singular only extraction.
 * import gettext from "warehouse/utils/fetch-gettext";
 * // Name the function ngettext for singular and plural extraction.
 * import ngettext from "warehouse/utils/fetch-gettext";
 * // For a singular only string:
 * gettext("Just now");
 * // For a singular and plural and placeholder string:
 * ngettext("About a minute ago", "About ${numMinutes} minutes ago", numMinutes, {"numMinutes": numMinutes});

 * @param singular {string} The default string for the singular translation.
 * @param plural {string} The default string for the plural translation.
 * @param num {number} The number to use to select the appropriate translation.
 * @param values {object} Key value pairs to fill the placeholders.
 * @returns {Promise<any | string>} The Fetch API promise.
 * @see https://www.gnu.org/software/gettext/manual/gettext.html#Language-specific-options
 * @see https://docs.pylonsproject.org/projects/pyramid/en/latest/api/i18n.html#pyramid.i18n.Localizer.pluralize
 */
export default (singular, plural, num, values) => {
  const partialMsg = `for singular '${singular}', plural '${plural}', num '${num}', values '${JSON.stringify(values || {})}'`;
  let searchValues = {s: singular};
  if (plural) {
    searchValues.p = plural;
  }
  if (num !== undefined) {
    searchValues.n = num;
  }
  if (values !== undefined) {
    searchValues = {...searchValues, ...values};
  }
  const searchParams = new URLSearchParams(searchValues);
  return fetch("/translation?" + searchParams.toString(), fetchOptions)
    .then(response => {
      if (response.ok) {
        const responseJson = response.json();
        console.debug(`Fetch gettext success ${partialMsg}: ${responseJson}.`);
        return responseJson;
      } else {
        console.warn(`Fetch gettext unexpected response ${partialMsg}: ${response.status}.`);
        return "";
      }
    }).catch((err) => {
      console.error(`Fetch gettext failed ${partialMsg}: ${err.message}.`);
      return "";
    });
};
