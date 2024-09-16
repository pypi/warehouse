/*
 * Licensed under the Apache License, Version 2.0 (the "License");
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

// Ref https://adminlte.io/docs/3.2/javascript/treeview.html

// Enable sidebar treeview active links
$(function() {
  const url = window.location;

  const element = $("aside nav ul a").filter(function () {
    return this.href === url.href;
  }).addClass("active").parent().parent().parent().addClass("menu-open").parent();
  if (element.is("li")) {
    element.addClass("active");
  }
});
