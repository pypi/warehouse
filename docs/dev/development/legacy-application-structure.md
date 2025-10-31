Legacy Application URL Structure
================================

Note: this is a brain dump, mostly written by Donald Stufft in early 2015.

It *just* lists the legacy structure and none of the intended new structure.

The following documents the current URLs in the legacy PyPI application.

============= =================================================================
URL           Purpose
------------- -----------------------------------------------------------------
/             Redirect to /pypi
/pypi         Legacy PyPI application. See below.
/daytime      Legacy mirroring support
/security     Page giving contact and other information regarding site security
/id           OpenID endpoint
/oauth        OAuth endpoint
/simple       Simple API as given in `Index API <https://docs.pypi.org/api/index-api/>`_
/packages     Serve up a package file
/mirrors      Page listing legacy mirrors (not to be retained)
/serversig    Legacy mirroring support (no-one uses it: not to be retained)
/raw-packages nginx implementation specific hackery (entirely internal; not to
              be retained)
/stats        Web stats. Whatever. Probably dead.
/local-stats  Package download stats. All the legacy mirrors have this.
/static       Static files (CSS, images) in support of the web interface.
============= =================================================================

The legacy application has a bunch of different behaviours:

1. With no additional path, parameter or content-type information the app
   renders a "front page" for the site. TODO: keep this behaviour or redirect?
2. With a content-type of "text/xml" the app runs in an XML-RPC server mode.
3. With certain path information the app will render project information.
4. With an :action parameter the app will take certain actions and/or display
   certain information.

The :action parameters are typically submitted through GET URL parameters,
though some actions are also POST actions.

**could be nuked without fuss**
  - ``display`` was used to display a package version but was replaced ages ago
    by the /<package>/<version> URL structure
  - all the user-based stuff like ``register_form``, ``user``, ``user_form``,
    ``forgotten_password_form``, ``login``, ``logout``, ``forgotten_password``,
    ``password_reset``, ``pw_reset`` and ``pw_reset_change`` will most likely be
    replaced by newer mechanisms in warehouse
  - ``openid_endpoint``, ``openid_decide_post`` could also be replaced by something
    else.
  - ``home`` is the old home page thing and completely unnecessary
  - ``index`` is overwhelming given the number of projects now.
  - ``browse`` and ``search`` are *probably* only referenced by internal links so
    should be safe to nuke
  - ``submit_pkg_info`` and ``display_pkginfo`` probably aren't used
  - ``submit_form`` and ``pkg_edit`` will be changing anyway
  - ``files``, ``urls``, ``role``, ``role_form`` are old style and will be changing
  - ``list_classifiers`` .. this might actually only be used by Richard :)
  - ``claim``, ``openid``, ``openid_return``, ``dropid`` are legacy openid login
    support and will be changing
  - ``clear_auth`` "clears" Basic Auth
  - ``addkey``, ``delkey`` will be changing if we even keep supporting ssh submit
  - ``verify`` probably isn't actually used by anyone
  - ``lasthour`` is a pubsubhubbub thing - does this even exist any longer?
  - ``json`` is never used as a :action invocation, only ever /<package>/json
  - ``gae_file`` I'm pretty sure this is not necessary
  - ``rss_regen`` manually regens the RSS cached files, not needed
  - ``about`` No longer needed.
  - ``delete_user`` No longer needed.
  - ``exception`` No longer needed.

**will need to retain**
  - ``rss`` and ``packages_rss`` will be in a bunch of peoples` RSS readers
  - ``doap`` is most likely referred to
  - ``show_md5`` ?

**can be deprecated carefully**
  - ``submit``, ``upload``, ``doc_upload``, ``file_upload``,
