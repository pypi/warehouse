PyPI's json methods
===================

Example usage::

  >>> import json
  >>> import requests
  >>> url = 'https://pypi.python.org/pypi/roundup/json'
  >>> pkg_info = json.loads(requests.get(url).content)['info']
  >>> print(pkg_info['version'])
  1.5.1
  >>> print(pkg_info['release_url'])
  http://pypi.python.org/pypi/roundup/1.5.1
  >>> print(pkg_info['home_page'])
  http://www.roundup-tracker.org

  >>> url = 'https://pypi.python.org/pypi/roundup/1.3.1/json'
  >>> pkg_info = json.loads(requests.get(url).content)['info']
  >>> print(pkg_info['version'])
  1.3.1
  >>> print(pkg_info['release_url'])
  http://pypi.python.org/pypi/roundup/1.3.1
  >>> print(pkg_info['home_page'])
  http://roundup.sourceforge.net/
