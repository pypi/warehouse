# Note: It is VERY important to ensure that any changes to VCL will work
#       properly with both the current version of ``master`` and the version in
#       the pull request that adds any new changes. This is because the
#       configuration will be applied automatically as part of the deployment
#       process, but while the previous version of the code is still up and
#       running. Thus backwards incompatible changes must be broken up over
#       multiple pull requests in order to phase them in over multiple deploys.

sub vcl_recv {

    # I'm not 100% sure on what this is exactly for, it was taken from the
    # Fastly documentation, however, what I *believe* it does is just ensure
    # that we don't serve a stale copy of the page from the shield node when
    # an edge node is requesting content.
    if (req.http.Fastly-FF) {
        set req.max_stale_while_revalidate = 0s;
    }

    # Some (Older) clients will send a hash fragment as part of the URL even
    # though that is a local only modification. This breaks this badly for the
    # files in S3, and in general it's just not needed.
    set req.url = regsub(req.url, "#.*$", "");

    # Fastly does some normalization of the Accept-Encoding header so that it
    # reduces the number of cached copies (when served with the common,
    # Vary: Accept-Encoding) that are cached for any one URL. This makes a lot
    # of sense, except for the fact that we want to enable brotli compression
    # for our static files. Thus we need to work around the normalized encoding
    # in a way that still minimizes cached copies, but which will allow our
    # static files to be served using brotli.
    if (req.url ~ "^/static/" && req.http.Fastly-Orig-Accept-Encoding) {
        if (req.http.User-Agent ~ "MSIE 6") {
            # For that 0.3% of stubborn users out there
            unset req.http.Accept-Encoding;
        } elsif (req.http.Fastly-Orig-Accept-Encoding ~ "br") {
            set req.http.Accept-Encoding = "br";
        } elsif (req.http.Fastly-Orig-Accept-Encoding ~ "gzip") {
            set req.http.Accept-Encoding = "gzip";
        } else {
            unset req.http.Accept-Encoding;
        }
    }

    # Most of the URLs in Warehouse do not support or require any sort of query
    # parameter. If we strip these at the edge then we'll increase our cache
    # efficiency when they won't otherwise change the output of the pages.
    #
    # This will match any URL except those that start with:
    #
    #   * /admin/
    #   * /search/
    #   * /account/login/
    #   * /account/logout/
    #   * /account/register/
    #   * /pypi
    if (req.url.path !~ "^/(admin/|search(/|$)|account/(login|logout|register)/|pypi)") {
        set req.url = req.url.path;
    }

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

    # Redirect pypi.io, www.pypi.io, and warehouse.python.org to pypi.org, this
    # is purposely done *after* the HTTPS checks.
    if (std.tolower(req.http.host) ~ "^(www.pypi.org|(www.)?pypi.io|warehouse.python.org)$") {
        set req.http.Location = "https://pypi.org" req.url;
        error 750 "Redirect to Primary Domain";
    }
    # Redirect warehouse-staging.python.org to test.pypi.io.
    if (std.tolower(req.http.host) ~ "^(test.pypi.io|warehouse-staging.python.org)$") {
        set req.http.Location = "https://test.pypi.org" req.url;
        error 750 "Redirect to Primary Domain";
    }

    # Requests to /packages/ get dispatched to Amazon instead of to our typical
    # Origin. This requires a a bit of setup to make it work.
    if (req.http.host ~ "^(test-)?files.pythonhosted.org$"
            && req.url ~ "^/packages/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{60}/") {
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
            set req.http.Warehouse-Host = req.http.host;
        }
    }

    # On a POST, we want to skip the shielding and hit backends directly.
    if (req.request == "POST") {
        set req.backend = F_Heroku;
    }

    # Do not bother to attempt to run the caching mechanisms for methods that
    # are not generally safe to cache.
    if (req.request != "HEAD" &&
        req.request != "GET" &&
        req.request != "FASTLYPURGE") {
      return(pass);
    }

    # We don't ever want to cache our health URL. Outside systems should be
    # able to use it to reach past Fastly and get an end to end health check.
    if (req.url == "/_health/") {
        return(pass);
    }

    # We never want to cache our admin URLs, while this should be "safe" due to
    # the architecure of Warehouse, it'll just be easier to debug issues if
    # these always are uncached.
    if (req.url ~ "^/admin/") {
        return(pass);
    }

    # Finally, return the default lookup action.
    return(lookup);
}


sub vcl_fetch {

    # These are newer kinds of redirects which should be able to be cached by
    # default, even though Fastly doesn't currently have them in their default
    # list of cacheable status codes.
    if (http_status_matches(beresp.status, "303,307,308")) {
        set beresp.cacheable = true;
    }

    # For any 5xx status code we want to see if a stale object exists for it,
    # if so we'll go ahead and serve it.
    if (beresp.status >= 500 && beresp.status < 600) {
        if (stale.exists) {
            return(deliver_stale);
        }
    }

    # When delivering a 304 response, we don't always have access to all the
    # headers in the resp because a 304 response is supposed to remove most of
    # the headers. So we'll instead stash these headers on the request so that
    # we can log this data from there instead of from the response.
    if (beresp.http.x-amz-meta-project
            || beresp.http.x-amz-meta-version
            || beresp.http.x-amz-meta-package-type) {
        set req.http.Fastly-amz-meta-project = beresp.http.x-amz-meta-project;
        set req.http.Fastly-amz-meta-version = beresp.http.x-amz-meta-version;
        set req.http.Fastly-amz-meta-package-type = beresp.http.x-amz-meta-package-type;
    }


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
    if (http_status_matches(beresp.status, "500,502,503")) {
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


sub vcl_hit {
#FASTLY hit

    # If the object we have isn't cacheable, then just serve it directly
    # without going through any of the caching mechanisms.
    if (!obj.cacheable) {
        return(pass);
    }

    return(deliver);
}


sub vcl_deliver {
    # If this is an error and we have a stale response available, restart so
    # that we can pick it up and serve it.
    if (resp.status >= 500 && resp.status < 600) {
        if (stale.exists) {
            restart;
        }
    }

#FASTLY deliver

    # Unset headers that we don't need/want to send on to the client because
    # they are not generally useful.
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

    # Unstash our information about what project/version/package-type a
    # particular file download was for.
    if (req.http.Fastly-amz-meta-project
            || req.http.Fastly-amz-meta-version
            || req.http.Fastly-amz-meta-package-type) {
        set resp.http.x-amz-meta-project = req.http.Fastly-amz-meta-project;
        set resp.http.x-amz-meta-version = req.http.Fastly-amz-meta-version;
        set resp.http.x-amz-meta-package-type = req.http.Fastly-amz-meta-package-type;
    }

    # If we're not executing a shielding request, and the URL is one of our file
    # URLs, and it's a GET request, and the response is either a 200 or a 304
    # then we want to log an event stating that a download has taken place.
    if (!req.http.Fastly-FF
            && std.tolower(req.http.host) == "files.pythonhosted.org"
            && req.url.path ~ "^/packages/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{60}/"
            && req.request == "GET"
            && http_status_matches(resp.status, "200,304")) {
        log {"syslog "} req.service_id {" linehaul :: "} "2@" now "|" geoip.country_code "|" req.url.path "|" tls.client.protocol "|" tls.client.cipher "|" resp.http.x-amz-meta-project "|" resp.http.x-amz-meta-version "|" resp.http.x-amz-meta-package-type "|" req.http.user-agent;
        log {"syslog "} req.service_id {" downloads :: "} "2@" now "|" geoip.country_code "|" req.url.path "|" tls.client.protocol "|" tls.client.cipher "|" resp.http.x-amz-meta-project "|" resp.http.x-amz-meta-version "|" resp.http.x-amz-meta-package-type "|" req.http.user-agent;
    }

    return(deliver);
}


sub vcl_error {
#FASTLY error

    # If we have a 5xx error and there is a stale object available, then we
    # will deliver that stale object.
    if (obj.status >= 500 && obj.status < 600) {
        if (stale.exists) {
            return(deliver_stale);
        }
    }

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
