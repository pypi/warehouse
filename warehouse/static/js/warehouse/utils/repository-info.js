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

export default () => {
  const services = [
    {wrapper: ".github-repo-info", items: ".github-repo-info__item"},
    {wrapper: ".gitlab-repo-info", items: ".gitlab-repo-info__item"},
  ];
  services.forEach((service) => {
    let repoInfoContainer = document.querySelector(service.wrapper);
    if (repoInfoContainer !== null){
      const url = repoInfoContainer.dataset.url;
      fetch(url, {
        method: "GET",
        mode: "cors",
      }).then((response) => {
        if (response.ok){
          return response.json();
        } else {
          return null;
        }
      }).then((json) => {
        if (json === null){
          return;
        }
        repoInfoContainer.classList.remove("hidden");
        const items = document.querySelectorAll(service.items);
        items.forEach(function(elem) {
          const jsonKey = elem.dataset.key;
          let jsonValue = json[jsonKey];
          if(jsonValue !== undefined){
            const supplement = elem.dataset.supplement;
            if (supplement !== undefined) {
              jsonValue += supplement;
            }
            if (jsonKey.includes("_count")) {
              // Number formatting for count keys.
              jsonValue = jsonValue.toLocaleString();
            }
            const attr = elem.dataset.attr;
            if (attr !== undefined) {
              elem[attr] = jsonValue;
            } else {
              elem.innerText = jsonValue;
            }
          }
        }, this);
      }).catch(function() {

      });
    }
  });
};
