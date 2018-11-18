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

/* global fixture */

import { Application } from "stimulus";

function registerApplication(id, controllerClass, fixtureName) {
  fixtureName = fixtureName || id;
  fixture.load(`${fixtureName}.html`);
  this._stimulusApp = new Application();
  this._stimulusApp.router.start();
  this._stimulusApp.register(id, controllerClass);
  this.controller = this._stimulusApp.controllers[0];
}

export { registerApplication };

