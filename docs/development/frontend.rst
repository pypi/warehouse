Frontend
========

The Warehouse frontend is (as you might suspect) written in javascript with the
CSS handled by SCSS. It uses gulp to process these files and prepare them for
serving.

All of the static files are located in ``warehouse/static/`` and external
libraries are found in ``bower.json``.


Building
--------

Static files should be automatically built when ``make serve`` is running,
however you can trigger a manual build of them by installing all of the
dependencies using ``npm install`` and then running ``gulp dist``.


Browser Support
---------------

========= ====================
 Browser  Supported Versions
========= ====================
 Chrome   Current, Current - 1
 Firefox  Current, Current - 1
 Edge     Current, Current - 1
 Opera    Current, Current - 1
 Safari   9.0+
 IE       11+
========= ====================
