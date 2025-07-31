/* SPDX-License-Identifier: Apache-2.0 */

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
