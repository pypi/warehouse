---
name: Network Access Issues
about: Let us know if you're having trouble reaching PyPI 

---

<!--
    NOTE: This issue should be for problems accessing PyPI itself, including:
    * pypi.org
    * test.pypi.org
    * files.pythonhosted.org

    This issue should NOT be for any non-PyPI properties (like
    python.org, docs.python.org, etc.)
-->

## My Platform
<!--
    Any details about your specific platform:
    * If the problem is in the browser, what browser, version, and OS?
    * If the problem is with a command-line tool, what version of that tool?
    * If the problem is with connecting to PyPI, include some details about
      your network, including SSL/TLS implementation in use, internet service
      provider, and if there are any firewalls or proxies in use.
-->

## Network telemetry
<!--
    Providing this information is crucial in helping diagnose networking
    issues for PyPI.
-->

<!--
### Fastly Debug
    Note that this output is optional, as it encodes identifying information
    about your browser, public IP, and location.

    We'll remove this output from the issue before closing, but do not feel
    comfortable making it required for all users.

    If you have a browser that reproduces your access issue, go to
    https://fastly-debug.com, when the page has loaded copy and paste the
    base64 encoded blob at the top of the page into the box below, and
    uncomment this section.

    Note that you may need to disable ad-blockers and privacy protection
    extensions in order for this page to operate, as it makes numerous calls
    to servers on our CDN's network that look concerning to those tools.

```
<Replace with your output>
```
-->

### DNS Resolution

<!--
    Provide the servers you're querying for DNS here if you know. They can be
    found in /etc/resolv.conf on most linux servers, or your network settings
    for MacOS and Windows.

    dig is used for these examples, if you are familiar with another tool that
    performs a similar utility, please provide that output.
-->

```shell
dig pypi.org A
<Replace with your output>
```

```shell
dig pypi.org AAAA
<Replace with your output>
```

```shell
dig files.pythonhosted.org A
<Replace with your output>
```

```shell
dig files.pythonhosted.org AAAA
<Replace with your output>
```

### Traceroutes

<!--
    traceroute is used for these examples, if you are familiar with another tool
    that performs a similar utility, please provide that output.
-->

#### IPv4

```shell
traceroute pypi.org
<Replace with your output>
```

```shell
traceroute files.pythonhosted.org
<Replace with your output>
```

#### IPv6 (If available)

```shell
traceroute6 pypi.org
<Replace with your output>
```

```shell
traceroute6 files.pythonhosted.org
<Replace with your output>
```

### HTTPS Requests

<!--
    These provide a more holistic view of what is going on, and the ways that
    PyPI is generally accessed. They can also provide insight into TLS issues
    that may be occuring.
-->

#### IPv4

```shell
curl -vvv -I --ipv4 https://pypi.org/pypi/pip/json
<Replace with your output>
```

```shell
curl -vvv -I --ipv4 https://files.pythonhosted.org/packages/ae/e8/2340d46ecadb1692a1e455f13f75e596d4eab3d11a57446f08259dee8f02/pip-10.0.1.tar.gz
<Replace with your output>
```

#### IPv6 (If available)

```shell
curl -vvv -I --ipv6 https://pypi.org/pypi/pip/json
<Replace with your output>
```

```shell
curl -vvv -I --ipv6 https://files.pythonhosted.org/packages/ae/e8/2340d46ecadb1692a1e455f13f75e596d4eab3d11a57446f08259dee8f02/pip-10.0.1.tar.gz
<Replace with your output>
```

### TLS Debug

#### IPv4

```shell
echo -n | openssl s_client -4 -connect pypi.org:443
<Replace with your output>
```

```shell
echo -n | openssl s_client -4 -connect files.pythonhosted.org:443
<Replace with your output>
```

#### IPv6 (If available)

```shell
echo -n | openssl s_client -6 -connect pypi.org:443
<Replace with your output>
```

```shell
echo -n | openssl s_client -6 -connect files.pythonhosted.org:443
<Replace with your output>
```
