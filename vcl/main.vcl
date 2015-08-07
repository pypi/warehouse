
sub vcl_recv {
#FASTLY recv

    # We want to Force SSL for the WebUI by redirecting to the HTTPS version of
    # the page, however for API calls we want to return an error code directing
    # people to instead use HTTPS.
    # TODO: Cause an error instead of a redirect for "API" URLs.
    if (!req.http.Fastly-SSL) {
        error 801 "Force SSL";
    }

    # Do not bother to attempt to run the caching mechanisms for methods that
    # are not generally safe to cache.
    if (req.request != "HEAD" &&
        req.request != "GET" &&
        req.request != "FASTLYPURGE") {
      return(pass);
    }

    # Finally, return the default lookup action.
    return(lookup);
}
