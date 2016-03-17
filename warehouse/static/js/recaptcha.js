function renderCaptcha() {
    var config = new Object();
    config.sitekey = $("script#recaptcha-js").data("site-key");
    grecaptcha.render($("#recaptcha-container")[0], config);
}
