export default () => {
  const mobileBtn = document.querySelector(".-js-vertical-tab-mobile-heading");
  const styleProps = getComputedStyle(mobileBtn, null);
  const inMobileState = (styleProps.getPropertyValue("display") === "block");
  const btnClassName = inMobileState ? ".-js-vertical-tab-mobile-heading" : ".-js-vertical-tab";
  const activeClass = "vertical-tabs__tab--is-active";
  const getBtnByHref = (id) => document.querySelector(`${btnClassName}[href="#${id}"]`);
  const toggleTab = (clickedBtn, event) => {
    if (event) {
      event.preventDefault();
      history.pushState(null, "", clickedBtn.getAttribute("href"));
    }
    let id = clickedBtn.getAttribute("href").replace("#", "");
    // toggle display setting for the content related to the button
    for (var elem of document.querySelectorAll(".-js-vertical-tab-content")) {
      var btn = getBtnByHref(elem.id);
      if (elem.id === id) {
        elem.style.display = "block";
        btn.classList.add(activeClass);
      } else {
        elem.style.display = "none";
        btn.classList.remove(activeClass);
      }
    }
  };

  for (var btn of document.querySelectorAll(btnClassName)) {
    btn.addEventListener("click", toggleTab.bind(null, btn), false);
  }

  var initialContentId = location.hash ? location.hash.replace("#", "") : "description";
  var initialBtn = getBtnByHref(initialContentId);
  toggleTab(initialBtn);

  // I'm not sure if this is needed?
  window.addEventListener("hashchange", () => {
    var btn = getBtnByHref(location.hash.replace("#", ""));
    toggleTab(btn);
  }, false);

};
