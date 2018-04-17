# Note: This is *ONLY* used for test.pypi.org, for the pypi.org, see python/pypi-infra

# Note: It is VERY important to ensure that any changes to VCL will work
#       properly with both the current version of ``master`` and the version in
#       the pull request that adds any new changes. This is because the
#       configuration will be applied automatically as part of the deployment
#       process, but while the previous version of the code is still up and
#       running. Thus backwards incompatible changes must be broken up over
#       multiple pull requests in order to phase them in over multiple deploys.

sub vcl_recv {

    # Fastly is dropping support for TLSv1.0 and TLSv1.1, in preperation for
    # for that, we're going to block support for it now, using VCL. This will
    # let us present a better error message in the interim before Fastly shuts
    # off TLSv1.0 and TLSv1.1 support completely.
    if (tls.client.protocol ~ "^TLSv1(\.(0|1))?$") {
        set req.http.Error-Message = "Support for " tls.client.protocol " has been removed, please upgrade to a TLSv1.2+ client. Please see https://pyfound.blogspot.com/2017/01/time-to-upgrade-your-python-tls-v12.html";
        error 804 "Bad SSL Version";
    }

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
    #   * /account/reset-password/
    #   * /account/verify-email/
    #   * /pypi
    if (req.url.path !~ "^/(admin/|search(/|$)|account/(login|logout|register|reset-password|verify-email)/|pypi)") {
        set req.url = req.url.path;
    }

    # Sort all of our query parameters, this will ensure that the same query
    # parameters in a different order will end up being represented as the same
    # thing, reducing cache misses due to ordering differences.
    set req.url = boltsort.sort(req.url);

    # We have a number of items that we'll pass back to the origin.
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

    # Currently Fastly does not provide a way to access response headers when
    # the response is a 304 response. This is because the RFC states that only
    # a limit set of headers should be sent with a 304 response, and the rest
    # are SHOULD NOT. Since this stripping happens *prior* to vcl_deliver being
    # ran, that breaks our ability to log on 304 responses. Ideally at some
    # point Fastly offers us a way to access the "real" response headers even
    # for a 304 response, but for now, we are going to remove the headers that
    # allow a conditional response to be made. If at some point Fastly does
    # allow this, then we can delete this code.
    if (!req.http.Fastly-FF
            && std.tolower(req.http.Warehouse-Host) == "files.pythonhosted.org"
            && req.url.path ~ "^/packages/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{60}/") {
        unset req.http.If-None-Match;
        unset req.http.If-Modified-Since;
    }


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
    if (req.backend == F_S3 && req.http.host ~ "^(test-)?files.pythonhosted.org$"
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

    # Set our standard security headers, we do this in VCL rather than in
    # Warehouse itself so that we always get these headers, regardless of the
    # origin server being used.
    set resp.http.Strict-Transport-Security = "max-age=31536000; includeSubDomains; preload";
    set resp.http.X-Frame-Options = "deny";
    set resp.http.X-XSS-Protection = "1; mode=block";
    set resp.http.X-Content-Type-Options = "nosniff";
    set resp.http.X-Permitted-Cross-Domain-Policies = "none";

    # Currently Fastly does not provide a way to access response headers when
    # the response is a 304 response. This is because the RFC states that only
    # a limit set of headers should be sent with a 304 response, and the rest
    # are SHOULD NOT. Since this stripping happens *prior* to vcl_deliver being
    # ran, that breaks our ability to log on 304 responses. Ideally at some
    # point Fastly offers us a way to access the "real" response headers even
    # for a 304 response, but for now, we are going to remove the headers that
    # allow a conditional response to be made. If at some point Fastly does
    # allow this, then we can delete this code, and also allow a 304 response
    # in the http_status_matches() check further down.
    if (!req.http.Fastly-FF
            && std.tolower(req.http.Warehouse-Host) == "files.pythonhosted.org"
            && req.url.path ~ "^/packages/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{60}/") {
        unset resp.http.ETag;
        unset resp.http.Last-Modified;
    }

    # If we're not executing a shielding request, and the URL is one of our file
    # URLs, and it's a GET request, and the response is either a 200 or a 304
    # then we want to log an event stating that a download has taken place.
    if (!req.http.Fastly-FF
            && std.tolower(req.http.Warehouse-Host) == "files.pythonhosted.org"
            && req.url.path ~ "^/packages/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{60}/"
            && req.request == "GET"
            && http_status_matches(resp.status, "200")) {
        log {"syslog "} req.service_id {" linehaul :: "} "2@" now "|" geoip.country_code "|" req.url.path "|" tls.client.protocol "|" tls.client.cipher "|" resp.http.x-amz-meta-project "|" resp.http.x-amz-meta-version "|" resp.http.x-amz-meta-package-type "|" req.http.user-agent;
        log {"syslog "} req.service_id {" downloads :: "} "2@" now "|" geoip.country_code "|" req.url.path "|" tls.client.protocol "|" tls.client.cipher "|" resp.http.x-amz-meta-project "|" resp.http.x-amz-meta-version "|" resp.http.x-amz-meta-package-type "|" req.http.user-agent;
    }

    # Set X-Robots-Header for everything _but_ prod
    if (std.tolower(req.http.host) !~ "^pypi.org$") {
        set resp.http.X-Robots-Header = "noindex";
    }

    # Unset a few headers set by Amazon that we don't really have a need/desire
    # to send to clients.
    unset resp.http.x-amz-replication-status;
    unset resp.http.x-amz-meta-python-version;
    unset resp.http.x-amz-meta-version;
    unset resp.http.x-amz-meta-package-type;
    unset resp.http.x-amz-meta-project;


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
    } else if(obj.status == 804) {
        set obj.status = 403;
        set obj.response = "TLSv1.2+ is required";
        set obj.http.Content-Type = "text/plain; charset=UTF-8";
        synthetic req.http.Error-Message;
        return (deliver);
    } else if (obj.status == 750) {
        set obj.status = 301;
        set obj.http.Location = req.http.Location;
        set obj.http.Content-Type = "text/html; charset=UTF-8";
        synthetic {"<html><head><title>301 Moved Permanently</title></head><body><center><h1>301 Moved Permanently</h1></center></body></html>"};
        return(deliver);
    }

}
