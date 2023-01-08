/**
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
import { Controller } from "@hotwired/stimulus";

export default class extends Controller {
  static values = {
    packageName: String,
    projectVersion: String,
    indexUrl: String,
    packageValue: String,
  };

  static targets = ["settings", "command"];

  connect() {
    console.log(this.packageNameValue);
    console.log(this.projectVersionValue);
    console.log(this.indexUrlValue);
  }

  showSettings() {
    this.settingsTarget.classList.toggle("hidden");
  }

  updateCommand() {
    console.log(this);
    const selectedPackageManager = this.settingsTarget.querySelector(
      'input[name="package-manager"]:checked'
    );

    switch (selectedPackageManager.value) {
      case "pip":
        this.commandTarget.innerHTML = `pip install ${this.packageNameValue}${this.projectVersionValue}`;
        break;
      case "poetry":
        this.commandTarget.innerHTML = `poetry add ${this.packageNameValue}${this.projectVersionValue}`;
        break;
      case "pipenv":
        this.commandTarget.innerHTML = `pipenv install ${this.packageNameValue}${this.projectVersionValue}`;
        break;
      case "pdm":
        this.commandTarget.innerHTML = `pdm add ${this.packageNameValue}${this.projectVersionValue}`;
        break;
    }
  }
}
