.. _roadmap:

Roadmap and Sprints
===================

Roadmap
-------

As we develop Warehouse, here are our plans along the way. To talk
about them with us, please `contact us`_.

OTF grant work
~~~~~~~~~~~~~~

The current priority: `security, accessibility, and localization work
funded by the Open Technology Fund`_, starting with `two-factor
authentication for PyPI`_.

On GitHub: `Security milestone`_, `accessibility milestone`_,
`localisation milestone`_.

Package signing and detection/verification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We will work on further improving PyPI security with features such as
cryptographic signing, verifying files uploaded to and installed from
the index, and automatically detecting malicious uploads. `This work
is funded by a gift from Facebook.`_

See `package signing & detection/verification milestone`_ on GitHub.

Post legacy shutdown
~~~~~~~~~~~~~~~~~~~~
Issues that are unblocked now that legacy is dead (RIP).

See `issues marked with the post-legacy shutdown milestone`_ on GitHub.

Cool but not urgent
~~~~~~~~~~~~~~~~~~~

Wishlist.

See `issues marked with the cool-but-not-urgent milestone`_ on GitHub.

History
~~~~~~~

You can see `our past roadmap`_, focusing on replacing legacy PyPI, on
the PSF wiki.

Sprints
-------

Please check the Python wiki for a list of upcoming `sprints`_.

Sprint planners should consider the following checklist for organising events:

- Prior to the sprint, tag issues that you identify as appropriate for the
  attendees. Ensure you have a mix of short achievable tickets, and more
  complex issues. Do not tag issues that are still under discussion or require
  specification, unless core team members will be in attendance
- Prior to the sprint, organise with the Working Group to print stickers and/or
  other swag to give to participants
- If not provided by the venue, bring along snacks. Everybody loves snacks.
- If not provided by the venue, bring nametags. If possible, organise the
  facilitators to wear the same colored shirt, lanyard or hat, to be easily
  identified by the group.
- If possible, ask participants to install the codebase *prior* to the event.
  This will save on delays caused by many people downloading docker images at
  once.
- Use a whiteboard or large sheets of paper to direct participants towards the
  codebase, issue tracker and installation documentation. Keep track of merged
  PRs in the same location.
- Ask participants to comment on the issues they want to work on. This avoids a
  situation where two people are unknowingly working towards the same goal.
- Where possible, pair people to work on issues together. This is particularly
  useful for large issues, or for newer developers.

.. _`security, accessibility, and localization work funded by the Open Technology Fund`: https://pyfound.blogspot.com/2019/03/commencing-security-accessibility-and.html
.. _`two-factor authentication for PyPI`: https://github.com/pypa/warehouse/issues/996
.. _`Security milestone`: https://github.com/pypa/warehouse/milestone/13
.. _`accessibility milestone`: https://github.com/pypa/warehouse/milestone/15
.. _`localisation milestone`: https://github.com/pypa/warehouse/milestone/14
.. _`package signing & detection/verification milestone`: https://github.com/pypa/warehouse/milestone/16
.. _`This work is funded by a gift from Facebook.`: https://pyfound.blogspot.com/2018/12/upcoming-pypi-improvements-for-2019.html
.. _`issues marked with the post-legacy shutdown milestone`: https://github.com/pypa/warehouse/milestone/12
.. _`issues marked with the cool-but-not-urgent milestone`: https://github.com/pypa/warehouse/milestone/11
.. _`contact us`: https://github.com/pypa/warehouse/blob/master/README.rst#discussion
.. _`our past roadmap`: https://wiki.python.org/psf/WarehouseRoadmap
.. _`sprints`: https://wiki.python.org/psf/PackagingSprints
