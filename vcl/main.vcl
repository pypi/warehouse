
sub vcl_recv {
#FASTLY recv

    # We want to Force SSL for the WebUI by redirecting to the HTTPS version of
    # the page, however for API calls we want to return an error code directing
    # people to instead use HTTPS.
    if (!req.http.Fastly-SSL) {

        # The /simple/ and /packages/ API.
        if (req.url ~ "^/(simple|packages)") {
            error 803 "SSL is required";
        }

        # The Legacy JSON API.
        if (req.url ~ "^/pypi/.+/json$") {
            error 803 "SSL is required";
        }

        # The Legacy ?:action= API.
        if (req.url ~ "^/pypi.*(\?|&)=:action") {
            error 803 "SSL is required";
        }

        # If we're on the /pypi page and we've received something other than a
        # GET or HEAD request, then we have no way to determine if a particular
        # request is an API call or not because it'll be in the request body
        # and that isn't available to us here. So in those cases, we won't
        # do a redirect.
        if (req.url ~ "^/pypi") {
            if (req.request == "GET" || req.request == "HEAD") {
                error 801 "Force SSL";
            }
        }
        else {
            # This isn't a /pypi URL so we'll just unconditionally redirect to
            # HTTPS.
            error 801 "Force SSL";
        }
    }

    # Set a header to tell the backend if we're using https or http.
    if (req.http.Fastly-SSL) {
        set req.http.Warehouse-Proto = "https";
    } else {
        set req.http.Warehouse-Proto = "http";
    }

    # Pass the client IP address back to the backend.
    if (req.http.Fastly-Client-IP) {
        set req.http.Warehouse-IP = req.http.Fastly-Client-IP;
    }

    # Pass the real host value back to the backend.
    if (req.http.Host) {
        set req.http.Warehouse-Host = req.http.Host;
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


sub vcl_fetch {
#FASTLY fetch

    # Trigger a "SSL is required" error if the backend has indicated to do so.
    if (beresp.http.X-Fastly-Error == "803") {
        error 803 "SSL is required";
    }

    # If we've gotten a 502 or a 503 from the backend, we'll go ahead and retry
    # the request.
    if ((beresp.status == 502 || beresp.status == 503) &&
            req.restarts < 1 &&
            (req.request == "GET" || req.request == "HEAD")) {
        restart;
    }

    # If we've restarted, then we'll record the number of restarts.
    if(req.restarts > 0 ) {
        set beresp.http.Fastly-Restarts = req.restarts;
    }

    # If there is a Set-Cookie header, we'll ensure that we do not cache the
    # response.
    if (beresp.http.Set-Cookie) {
        set req.http.Fastly-Cachetype = "SETCOOKIE";
        return (pass);
    }

    # If the response has the private Cache-Control directive then we won't
    # cache it.
    if (beresp.http.Cache-Control ~ "private") {
        set req.http.Fastly-Cachetype = "PRIVATE";
        return (pass);
    }

    # If we've gotten an error after the restarts we'll deliver the response
    # with a very short cache time.
    if (beresp.status == 500 || beresp.status == 503) {
        set req.http.Fastly-Cachetype = "ERROR";
        set beresp.ttl = 1s;
        set beresp.grace = 5s;
        return (deliver);
    }

    # Apply a default TTL if there isn't a max-age or s-maxage.
    if (beresp.http.Expires ||
            beresp.http.Surrogate-Control ~ "max-age" ||
            beresp.http.Cache-Control ~"(s-maxage|max-age)") {
        # Keep the ttl here
    }
    else {
        # Apply the default ttl
        set beresp.ttl = 60s;
    }

    # Actually deliver the fetched response.
    return(deliver);
}


sub vcl_deliver {
#FASTLY deliver

    # Unset headers that we don't need/want to send on to the client because
    # they are not generally useful.
    unset resp.http.Server;
    unset resp.http.Via;

    return(deliver);
}


sub vcl_error {
#FASTLY error

    if (obj.status == 803) {
        set obj.status = 403;
        set obj.response = "SSL is required";
        set obj.http.Content-Type = "text/plain; charset=UTF-8";
        synthetic {"SSL is required."};
        return (deliver);
    }

}
