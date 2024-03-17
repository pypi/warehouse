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
