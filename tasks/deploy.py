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
import io
import json
import textwrap

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
    ssh.run("apt-get install -q -y git dpkg-sig reprepro nginx")
    ssh.run("apt-get install node-less")
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

    # Upload our private key
    ssh.put("warehouse.key", "~/warehouse.key")

    # Import our private key
    ssh.run("gpg --allow-secret-key-import --import ~/warehouse.key")

    ssh.put(
        io.BytesIO(textwrap.dedent("""
            server {
                listen 80 default_server;
                root /var/www/warehouse-repository;
                autoindex on;
            }
        """)),
        "/etc/nginx/sites-available/default",
    )

    ssh.run("/etc/init.d/nginx restart")


def _build_package():
    # Clean any existing builds
    ssh.run("rm -rf /opt/warehouse")
    ssh.run("rm -rf ~/packages")

    # Create target directories
    ssh.run("mkdir -p /opt/warehouse")
    ssh.run("mkdir -p /opt/warehouse/etc")
    ssh.run("mkdir -p /opt/warehouse/var/www")

    # Create a virtual environment
    ssh.run("virtualenv -p pypy /opt/warehouse")

    # Install the latest Warehouse into environment
    ssh.run(
        "/opt/warehouse/bin/pip install "
        "--use-wheel --no-allow-external --download-cache=~/.pip/cache "
        "warehouse"
    )

    # Write out Build Time Configuration
    ssh.put(
        io.BytesIO(textwrap.dedent("""
            assets:
                directory: /opt/warehouse/var/www/static
        """).strip() + "\n"),
        "/opt/warehouse/etc/warehouse.build.yml",
    )

    # Run the collectstatic command
    ssh.run(
        "/opt/warehouse/bin/warehouse "
        "-c /opt/warehouse/etc/warehouse.build.yml collectstatic"
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
            "/opt/warehouse".format(version),
        )


def _upload_package():
    # Create the repository coniguration
    ssh.run("mkdir -p /var/www/warehouse-repository/conf")
    ssh.put(
        io.BytesIO(textwrap.dedent("""
            Codename: precise
            Components: main
            Architectures: amd64
            SignWith: yes
        """).strip()),
        "/var/www/warehouse-repository/conf/distributions",
    )

    # Sign the built packages
    ssh.run("dpkg-sig -k 024D2E77 --sign builder ~/packages/*.deb")

    # Add the package to the repository
    ssh.run(
        "reprepro -Vb /var/www/warehouse-repository --keepunreferencedfiles "
        "includedeb precise ~/packages/*.deb",
    )


@invoke.task
def provision():
    # Set the credentials for pyrax
    pyrax.set_setting("identity_type", "rackspace")
    pyrax.set_credential_file(".pyrax.cfg")

    # Provision the server with Rackspace
    server = pyrax.cloudservers.servers.create(
        "warehouse-repository",
        IMAGE_ID,
        FLAVOR_ID,
    )

    # Store the password
    fabric.state.env.password = server.adminPass

    # Wait until the server is built
    server = pyrax.utils.wait_for_build(server)

    fabric.state.env.host_string = "root@{}".format(
        filter(lambda x: "." in x, server.networks["public"])[0],
    )

    # Bootstrap our environment
    _bootstrap_environment()

    # Write out our config
    with open(".rackspace.json", "w") as rs:
        json.dump(
            {
                "host_string": fabric.state.env.host_string,
                "password": fabric.state.env.password,
            },
            rs,
        )


@invoke.task
def build():
    # Load our credentials
    with open(".rackspace.json") as rs:
        creds = json.load(rs)

    fabric.state.env.host_string = creds["host_string"]
    fabric.state.env.password = creds["password"]

    # Update our environment
    ssh.run("apt-get update -q -y")
    ssh.run("apt-get dist-upgrade -q -y")

    # Build the package
    _build_package()

    # Upload package
    _upload_package()


@invoke.task()
def chef():
    fabric.state.env.host_string = "pypi.psf.io"
    ssh.sudo("chef-client")


@invoke.task(default=True, pre=["deploy.build", "deploy.chef"])
def all():
    pass
