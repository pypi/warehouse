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
  const trendingElements = document.getElementsByClassName(
    "hide-by-index-trending"
  );
  const latestElements = document.getElementsByClassName(
    "hide-by-index-latest"
  );
  for (let i = 5; i <= 20; i++) {
    if (trendingElements[i]) {
      trendingElements[i].style.display = "none";
    }
    if (latestElements[i]) {
      latestElements[i].style.display = "none";
    }
  }
};
