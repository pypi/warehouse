// Setup MutationObserver shim since jsdom doesn't
// support it out of the box.

const fs = require("fs");
const path = require("path");

const shim = fs.readFileSync(
  path.resolve(
    "node_modules",
    "mutationobserver-shim",
    "dist",
    "mutationobserver.min.js"
  ),
  { encoding: "utf-8" }
);
const script = window.document.createElement("script");
script.textContent = shim;

window.document.body.appendChild(script);
