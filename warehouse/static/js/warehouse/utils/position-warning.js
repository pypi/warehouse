/* SPDX-License-Identifier: Apache-2.0 */

export default () => {
  const elm = document.querySelector(".js-stick-to-top");
  if (elm === null)
    return;
  const height = elm.offsetHeight;
  const elmBody = document.querySelector("body");
  if (elmBody === null)
    return;
  elmBody.style.paddingTop = height + "px";
  if (height) {
    elmBody.classList.add("with-sticky");
  }
};
