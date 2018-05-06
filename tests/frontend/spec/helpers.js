/* global fixture */

import { Application } from "stimulus";

function registerApplication(id, controllerClass, fixtureName) {
  fixtureName = fixtureName || id;
  fixture.load(`${fixtureName}.html`);
  this._stimulusApp = Application.start();
  this._stimulusApp.register(id, controllerClass);
  this.controller = this._stimulusApp.controllers[0];
}

export { registerApplication };
