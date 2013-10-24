# Copyright 2013 Donald Stufft
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import hashlib
import os

import fabric.api as ssh
import fabric.state
import invoke
import pyrax


IMAGE_ID = "25de7af5-1668-46fb-bd08-9974b63a4806"
FLAVOR_ID = "2"


def _bootstrap_environment():
    # Add the PyPy PPA
    ssh.run("add-apt-repository ppa:pypy/ppa -y")

    # Update Apt
    ssh.run("apt-get update -q -y")

    # Install requirements
    ssh.run("apt-get install -q -y pypy libpq-dev libffi-dev rubygems")
    ssh.run("apt-get install -q -y git-core")
    ssh.run(
        "curl https://bitbucket.org/pypa/setuptools/raw/bootstrap/ez_setup.py "
        "| pypy"
    )
    ssh.run(
        "curl https://raw.github.com/pypa/pip/master/contrib/get-pip.py "
        "| pypy"
    )
    ssh.run("gem install --no-ri --no-rdoc fpm")
    ssh.run("pip install virtualenv")


def _build_package():
    # Add our User
    ssh.run("useradd warehouse")

    # Create target directories
    ssh.run("mkdir -p /opt/warehouse")
    ssh.run("mkdir -p /opt/warehouse/etc")
    ssh.run("mkdir -p /opt/warehouse/var/www")

    # Create a virtual environment
    ssh.run("virtualenv -p pypy /opt/warehouse")

    # Install the latest Warehouse into environment
    ssh.run(
        "/opt/warehouse/bin/pip install "
        "--use-wheel --no-allow-external warehouse"
    )

    # Get the installed version of warehouse
    version = ssh.run(
        "/opt/warehouse/bin/python -c "
        "'import warehouse; print(warehouse.__version__)'",
    ).strip()

    # Make a directory for our built packages to go in
    ssh.run("mkdir -p ~/packages")

    with ssh.cd("~/packages"):
        ssh.run(
            "fpm -t deb -s dir -n warehouse -v {} --iteration 1 "
            "-m 'Donald Stufft <donald@stufft.io>' "
            "-d pypy -d libpq5 -d libffi6 "
            "--deb-user warehouse --deb-group warehouse "
            "/opt/warehouse".format(version),
        )


def _upload_package(storage):
    # Install depot which we need to manage the cloud files repository
    ssh.run("pip install git+https://github.com/dstufft/depot.git@cloudfiles")

    # Upload our private key
    ssh.put("warehouse.key", "~/warehouse.key")

    # Import our private key
    ssh.run("gpg --allow-secret-key-import --import ~/warehouse.key")

    with ssh.cd("~/packages"):
        with ssh.shell_env(DEPOT_STORAGE=storage):
            ssh.run("depot -c precise -k 024D2E77 *")


@invoke.task
def build():
    # Set the credentials for pyrax
    pyrax.set_setting("identity_type", "rackspace")
    pyrax.set_credential_file(".pyrax.cfg")

    # Provision the server with Rackspace
    server = pyrax.cloudservers.servers.create("build-{}".format(
        hashlib.md5(os.urandom(10)).hexdigest()[:7]),
        IMAGE_ID,
        FLAVOR_ID,
    )

    print("[local] Building server")

    try:
        # Store the password
        fabric.state.env.password = server.adminPass

        # Wait until the server is built
        server = pyrax.utils.wait_for_build(server)

        fabric.state.env.host_string = "root@{}".format(
            filter(lambda x: "." in x, server.networks["public"])[0],
        )

        # Construct our storage url
        storage = "cloudfiles-us://{}:{}@warehouse-apt".format(
            pyrax.identity.username,
            pyrax.identity.password,
        )

        # Bootstrap our environment
        _bootstrap_environment()

        # Build the package
        _build_package()

        # Upload package
        _upload_package(storage)
    finally:
        # We're done with the server, so delete it
        server.delete()


@invoke.task(default=True, pre=["deploy.build"])
def all():
    pass
