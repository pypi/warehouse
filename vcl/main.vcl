
sub vcl_recv {

    # Some (Older) clients will send a hash fragment as part of the URL even
    # though that is a local only modification. This breaks this badly for the
    # files in S3, and in general it's just not needed.
    set req.url = regsub(req.url, "#.*$", "");

    # Sort all of our query parameters, this will ensure that the same query
    # parameters in a different order will end up being represented as the same
    # thing, reducing cache misses due to ordering differences.
    set req.url = boltsort.sort(req.url);


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

    # Canonicalize our domains by redirecting any domain that doesn't match our
    # primary domain to our primary domain. We do this *after* the HTTPS check
    # on purpose.
    if (std.tolower(req.http.host) != std.tolower(req.http.Primary-Domain)) {
        set req.http.Location = "https://" req.http.Primary-Domain req.url;
        error 750 "Redirect to Primary Domain";
    }

    # Requests to /packages/ get dispatched to Amazon instead of to our typical
    # Origin. This requires a a bit of setup to make it work.
    if (req.url ~ "^/packages/") {
        # Setup our environment to better match what S3 expects/needs
        set req.http.Host = req.http.AWS-Bucket-Name ".s3.amazonaws.com";
        set req.http.Date = now;
        set req.url = regsuball(req.url, "\+", urlencode("+"));

        # Compute the Authorization header that S3 requires to be able to
        # access the files stored there.
        set req.http.Authorization = "AWS " req.http.AWS-Access-Key-ID ":" digest.hmac_sha1_base64(req.http.AWS-Secret-Access-Key, "GET" LF LF LF req.http.Date LF "/" req.http.AWS-Bucket-Name req.url.path);

        # We don't want to send our Warehouse-Token to S3, so we'll go ahead
        # and remove it.
        unset req.http.Warehouse-Token;
    }

    # We no longer need any of these variables, which would exist only to
    # shuffle configuration from the Fastly UI into our VCL.
    unset req.http.Primary-Domain;
    unset req.http.AWS-Access-Key-ID;
    unset req.http.AWS-Secret-Access-Key;
    unset req.http.AWS-Bucket-Name;

    # We have a number of items that we'll pass back to the origin, but only
    # if we have a Warehouse-Token that will allow them to be accepted.
    if (req.http.Warehouse-Token) {
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

    # Unset a few headers set by Amazon that we don't really have a need/desire
    # to send to clients.
    unset resp.http.X-AMZ-Replication-Status;
    unset resp.http.X-AMZ-Meta-Python-Version;
    unset resp.http.X-AMZ-Meta-Version;
    unset resp.http.X-AMZ-Meta-Package-Type;
    unset resp.http.X-AMZ-Meta-Project;

    # Set our standard security headers, we do this in VCL rather than in
    # Warehouse itself so that we always get these headers, regardless of the
    # origin server being used.
    set resp.http.Strict-Transport-Security = "max-age=31536000; includeSubDomains; preload";
    set resp.http.X-Frame-Options = "deny";
    set resp.http.X-XSS-Protection = "1; mode=block";
    set resp.http.X-Content-Type-Options = "nosniff";
    set resp.http.X-Permitted-Cross-Domain-Policies = "none";

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
    } else if (obj.status == 750) {
        set obj.status = 301;
        set obj.http.Location = req.http.Location;
        set obj.http.Content-Type = "text/html; charset=UTF-8";
        synthetic {"<html><head><title>301 Moved Permanently</title></head><body><center><h1>301 Moved Permanently</h1></center></body></html>"};
        return(deliver);
    }

}
