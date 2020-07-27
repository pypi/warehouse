Developing in the cloud
=======================

The Warehouse development environment requires at least 4GB of RAM. Some users
have struggled to make Warehouse performant during local development. This
page provides instructions on how to develop Warehouse in the cloud to avoid
resource constraints.

While these instructions are specfic to one developer's experience, they apply
to other cloud providers and IDEs.

Cloud server
------------

The first step is to get a Virtual Machine in the cloud. This could be an AWS
EC2 instance, GCP Compute Engine, Digital Ocean droplet, etc. In my
experience, a machine with 4GB RAM is sufficient if you only use it for
Warehouse.

Note that there is a monthly cost associated with these instances. I got a
suitable instance for $20 / month, and costs can be saved by terminating the
instance if you don't plan to use it for a few days.

Development setup
-----------------

SSH into the cloud server. Create a new SSH key on this server and associate
it with your Github account. Clone the Warehouse repo and go through the
normal setup instructions for building the Docker images and starting the
containers.

Open ports
----------

Ensure that all ports are open on the instance. If you don't want to do this,
at least open the ports that Warehouse uses.

With ``make serve`` running on the instance, visit the instance's public IP
in a web browser and verify that you can load the development Warehouse.
For instance, if the public IP of your instance is 134.122.111.11, visit
http://134.122.111.11:80 in the browser.

Edit code
---------

The final step is to edit code and see it immediately take effect. There are
two good options:

1. Edit code directly on the cloud server using an editor like vim or emacs
2. Edit code locally in an IDE that is connected to the server over SSH

I use option 2 with the VSCode `Remote SSH`_ extension. Other IDEs including
PyCharm offer similar features, though I haven't tried them.

.. _Remote SSH: https://code.visualstudio.com/docs/remote/ssh

Summary
-------

This development setup helps circumvent resource constraints while still
keeping the same convenient development workflows.
