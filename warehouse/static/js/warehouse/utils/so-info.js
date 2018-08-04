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
  const soInfoContainer = document.querySelector(".so-info");
  if (soInfoContainer !== null){
    const name = soInfoContainer.dataset.name;
    const requests = [{
        url: 'https://api.stackexchange.com/2.2/questions',
        queryParams: {
          "site": "stackoverflow",
          "filter": "total",
          "tagged": encodeURI(name)
        },
        dataKey: "questions_count"
      }, {
        url: 'https://api.stackexchange.com/2.2/search/advanced',
        queryParams: {
          "site": "stackoverflow",
          "filter": "total",
          "tagged": encodeURI(name),
          "accepted": "True"
        },
        dataKey: "answers_count"
      }
    ];
    requests.forEach((req) => {
      let url = new URL(req.url);
      url.search = new URLSearchParams(req.queryParams);
      fetch(url, {
        method: "GET",
        mode: "cors",
      }).then((response) => {
        if (response.ok){
          return response.json();
        }
      }).then((json) => {
        if(json.total > 0) {
          soInfoContainer.classList.remove("hidden");
        }
        const questions = document.querySelector(`.so-info__item [data-key="${req.dataKey}"]`);
        questions.innerText = json.total;
      })
    })
  }
};
