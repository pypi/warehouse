# Getting started

We're pleased that you are interested in working on Warehouse.

## Your first pull request

After you set up your development environment and ensure you can run
the tests and build the documentation (using the instructions in this
document), take a look at [our guide to the Warehouse codebase](../application.md). Then, look at our [open issues that are labelled "good first issue"](https://github.com/pypi/warehouse/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22), find one you want to work on, comment on it to say you're working on
it, then submit a pull request. Use our [submitting patches](submitting-patches.md) documentation
to help.

Setting up a development environment to work on Warehouse should be a
straightforward process. If you have any difficulty, contact us so we can
improve the process:

- For bug reports or general problems, file an issue on [GitHub](https://github.com/pypi/warehouse);
- For real-time chat with other PyPA developers, join `#pypa-dev` [on
  Libera](https://web.libera.chat/#pypa,#pypa-dev), or the [PyPA Discord](https://discord.gg/pypa);
- For longer-form questions or discussion, visit [Discourse](https://discuss.python.org/c/packaging/14).

## Detailed installation instructions

### Get the Warehouse source code

First, fork and clone the Warehouse source code to work on it locally.

[Fork](https://docs.github.com/en/get-started/quickstart/fork-a-repo) the repository
on [GitHub](https://github.com/pypi/warehouse) and
[clone](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository) it to
your local machine:

```shell
git clone git@github.com:YOUR-USERNAME/warehouse.git
```

Add a [remote](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/configuring-a-remote-for-a-fork) and
regularly [sync](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/syncing-a-fork) to make sure
you stay up-to-date with our repository:

```shell
git remote add upstream https://github.com/pypi/warehouse.git
git checkout main
git fetch upstream
git merge upstream/main
```

### Create your development environment

!!! note
    Warehouse development can be done using Makefile scripts which
    execute all developer actions inside Docker containers. You do
    not need to create a Python virtual environment.

#### Verify that you have Make installed

We use Make to build the docs and the Warehouse site.
Verify that you have Make installed in your environment.

```shell
make --version
```

If you do not have `Make` installed,
consult your operating system documentation on how to install `make`.

#### Do you want to build the docs or the Warehouse site?

If you wish to build the entire Warehouse site,
use Docker and follow the instructions below. However, if you are only
contributing to the user or development documentation, then you can skip
setting up Docker below and use `Make` instead. To build the docs,
follow the [instructions here](./documentation.md#local-development).

#### Why Docker?

Docker simplifies development environment set up.

Warehouse uses Docker and [Docker Compose](https://docs.docker.com/compose/)
to automate setting up a "batteries included" development environment. The
`Dockerfile` and `docker-compose.yml` files include all the
required steps for installing and configuring all the required external
services of the development environment.

#### Installing Docker

* Install [Docker Engine](https://docs.docker.com/engine/installation/)

The best experience for building Warehouse on Windows 10 is to use the
[Windows Subsystem for Linux](https://docs.microsoft.com/windows/wsl/) (WSL) in combination with both
[Docker for Windows](https://docs.docker.com/engine/installation/windows/) and [Docker for Linux](https://docs.docker.com/engine/installation/linux/). Follow the instructions
for both platforms.

#### Verifying Docker installation

Check that Docker is installed: `docker -v`

#### Install Docker Compose

Install Docker Compose using the Docker-provided
[installation instructions](https://docs.docker.com/compose/install/).

!!! note
    Docker Compose will be installed by [Docker for Mac](https://docs.docker.com/engine/installation/mac/) and
    [Docker for Windows](https://docs.docker.com/engine/installation/windows/) automatically.

#### Verifying Docker Compose installation

Check that Docker Compose is installed: `docker compose version`

#### Verifying the necessary ports are available

Warehouse needs access to a few local ports in order to run, namely ports
`80`, `5433`, and `9000`. You should check each of these for availability
with the `lsof` command.

For example, checking port `80`:

```shell
sudo lsof -i:80 | grep LISTEN
```

If the port is in use, the command will produce output, and you will need to
determine what is occupying the port and shut down the corresponding service.
Otherwise, the port is available for Warehouse to use, and you can continue.

Alternately, you may set the `WEB_PORT` environment variable for
`docker compose` to use instead. An example:

```shell
export WEB_PORT=8080
make ...

# or inline:
WEB_PORT=8080 make ...
```

### Building the Warehouse Container

Once you have Docker and Docker Compose installed, run:

```shell
make build
```

in the repository root directory.

This will pull down all of the required docker containers, build Warehouse and
run all of the needed services. The Warehouse repository will be mounted inside
the Docker container at `/opt/warehouse/src/`. After the initial build,
you should not have to run this command again.

### Running the Warehouse container and services

You have to start the Docker services that make up the Warehouse
application.

!!! tip
    These services need ~4 GB of RAM dedicated to Docker to work. This is more
    than the default setting of the Docker Engine of 2 GB. Thus, you
    need to increase the memory allocated to Docker in
    [Docker Preferences](https://docs.docker.com/docker-for-mac/#memory)
    (on Mac by moving the slider to 4 GB in the GUI) or [Docker Settings](https://docs.docker.com/docker-for-windows/#advanced)
    (on Windows by editing the config file found at `C:\Users\<USER>\AppData\Local\Docker\wsl`).

    If you are using Linux, you may need to configure the maximum map count to get
    the `opensearch` up and running. According to the
    [documentation](https://opensearch.org/docs/2.15/install-and-configure/install-opensearch/index/#important-settings)
    this can be set temporarily:

    ```shell
    # sysctl -w vm.max_map_count=262144
    ```

    or permanently by modifying the `vm.max_map_count` setting in your
    `/etc/sysctl.conf`.

    Also check that you have more than 5% disk space free, otherwise
    opensearch will become read only. See `flood_stage` in the
    [opensearch disk allocation docs](https://opensearch.org/docs/latest/install-and-configure/configuring-opensearch/cluster-settings/#cluster-level-routing-and-allocation-settings).

Once `make build` has finished,  run the command:

```shell
make serve
```

This command will:

* ensure the db is prepared,
* run migrations,
* load some example data from [Test PyPI](https://test.pypi.org/), and
* index all the data for the search database.
* start up the containers needed to run Warehouse

After the initial build process, you will only need this command each time you
want to startup Warehouse locally.

`make serve` will produce output for a while, and will not exit. Eventually
the output will cease, and you will see a log message indicating that either
the `web` service has started listening:

```console
warehouse-web-1   | [2022-12-26 19:27:12 +0000] [1] [INFO] Starting gunicorn 20.1.0
warehouse-web-1   | [2022-12-26 19:27:12 +0000] [1] [INFO] Listening at: http://0.0.0.0:8000 (1)
warehouse-web-1   | [2022-12-26 19:27:12 +0000] [1] [INFO] Using worker: sync
warehouse-web-1   | [2022-12-26 19:27:12 +0000] [7] [INFO] Booting worker with pid: 7
```

or that the `static` container has finished compiling the static assets:

```console
warehouse-static-1  |
warehouse-static-1  | webpack 5.75.0 compiled with 1 warning in 6610 ms
```

or maybe something else.

#### Bootstrapping the TUF Metadata Repository

To enable PyPI Index Signing ([PEP 458](https://peps.python.org/pep-0458/)),
you have to first bootstrap the TUF metadata repository.

```shell
make inittuf
```

You should see the following line at the bottom of the output:

```console
Bootstrap completed using `dev/rstuf/bootstrap.json`. 🔐 🎉
```

This command sends a static *bootstrap payload* to the RSTUF API. The payload
includes the TUF trust root for development and other configuration.

By calling this API, RSTUF creates the TUF metadata repository, installs the
TUF trust root for development, and creates the initial set of TUF metadata.

!!! note
    The RSTUF API is exposed only for development purposes and will not be
    available in production. Currently, no upload hooks or automatic metadata
    update tasks are configured to interact with RSTUF.

    Take a look at the [RSTUF API documentation](https://repository-service-tuf.readthedocs.io/en/stable/guide/general/usage.html#adding-artifacts)
    to see how you can simulate artifact upload or removal, and how they affect
    the TUF metadata repository:

    * RSTUF API: http://localhost:8001
    * TUF Metadata Repository: http://localhost:9001/tuf-metadata/

### Resetting the development database

```console
make resetdb
```

This command will fully reset the development database.

### Viewing Warehouse in a browser

At this point all the services are up, and web container is listening on port
80. It's accessible at http://localhost:80/.

!!! note
    If you are using `docker-machine` on an older version of macOS or
    Windows, the warehouse application might be accessible at
    `https://<docker-ip>:80/` instead. You can get information about the
    docker container with `docker-machine env`

!!! note
    On Firefox, the logos might show up as black rectangles due to  the
    *Content Security Policy* used and an implementation bug in Firefox (see
    [this bug report](https://bugzilla.mozilla.org/show_bug.cgi?id=1262842)
    for more info).

If you've set a different port via the `WEB_PORT` environment variable,
use that port instead.

### Logging in to Warehouse

You can log into warehouse at http://localhost:80/account/login/.

There are 4 accounts ready for you to use:

- `ewdurbin` - Superuser, 3 email addresses (one verified), has projects
- `di` - Superuser, 2 email addresses (both verified), has projects
- `dstufft` - Superuser, 2 email addresses (one verified), has projects
- `miketheman` - Regular user, 1 email address (not verified), has a project

The password for every account has been set to the string `password`.

Using different accounts will allow you to see different parts of the site,
and have slightly different experiences.

Note that there are no Moderator accounts in the dev db. Any Superuser can 
change a user to a moderator if needed.

#### TOTP and Recovery Codes

To generate a TOTP token, run the following from your terminal:

```shell
make totp
```
Alternatively, you can scan the QR code below to add these accounts to 
your authenticator app:

![TOTP QR Code](../assets/warehouse_admin_totp.png){ width="100" }

The following static recovery codes are pre-generated for these users:

```text
6ebc846aadf23e35
7283821faf191a33
68108e19d25e2eec
4e6a18adb880fbc1
f62627d29675725f
4cda895a133b4cc8
8678c6f0d9a1e6de
edc6ce3800c0fc94 -- burned
```

#### Email Verification

Auth verification emails are output to the console, or can be accessed 
from http://localhost:1080.

See [Testing Emails](email.md#testing-e-mails) for more information.


#### Logging in as users without 2FA

For users that are not listed above,
once logged in with the password `password`,
you must enroll in a form of Two-Factor Authentication (2FA).
This is a requirement for all users.

One way to make this easier is to use a command-line tool like
[totp-cli](https://yitsushi.github.io/totp-cli/) to generate a TOTP 2FA code.

For example, to generate a code for any of the above users,
we have a common Key set in the database for those users:

```shell
totp-cli instant <<< IU7UP3EMIPI7EBPQUUSEHEJUFNBIWOYG
```

This will emit a 6-digit code you can paste into the 2FA form.

For other accounts, you'll need to preserve the Key used
to genreate the TOTP code the next time you need to log in.

To be able to "forget" the initial Key, and use it like a TOTP app,
create a storage and set a password, like so:

```shellsession
$ totp-cli add-token localhost <username>
Token: <paste Key from warehouse web interface here>
Password: <set a password, is unique to this totp storage>
```

Then you can retrieve the current TOTP code with:

```shellsession
$ totp-cli g localhost <username>
Password: <the password you set for the totp storage>
```

Keep in mind: If the database is ever reset,
you'll need to re-enroll user accounts in 2FA.

Remove the existing TOTP token from storage with:

```shellsession
$ totp-cli delete localhost <username>
Password: <the password you set for the totp storage>
```

### Stopping Warehouse and other services

In the terminal where `make serve` is running, you can use `Control-C`
to gracefully stop all Docker containers, and thus the one running the
Warehouse application.

Or, from another terminal, use `make stop` in the Warehouse
repository root; that'll stop all the Docker processes with
`warehouse` in the name.

### What did we just do and what is happening behind the scenes?

The repository is exposed inside of the web container at
`/opt/warehouse/src/` and Warehouse will automatically reload
when it detects any changes made to the code.

The example data located in `dev/example.sql.xz` is taken from
[Test PyPI](https://test.pypi.org/) and has been sanitized to remove anything private.

## Running your developer environment after initial setup

You won't have to initialize the database after the first time you do
so, and you will rarely have to re-run `make build`. Ordinarily, to
access your developer environment, you'll:

```shell
make serve
```

View Warehouse in the browser at http://localhost:80/.

### Debugging the webserver

If you would like to use a debugger like pdb that allows you to drop
into a shell, you can use `make debug` instead of `make serve`.

## Troubleshooting

### Errors when executing `make build`

* If you are using Ubuntu and `invalid reference format` error is displayed,
  you can fix it by installing Docker through [Snap](https://snapcraft.io/docker).

    ```shell
    snap install docker
    ```

### Errors when executing `make serve`

* If the `Dockerfile` is edited or new dependencies are added
  (either by you or a prior pull request), a new container will need
  to built. A new container can be built by running `make
  build`. This should be done before running `make serve` again.

* If `make serve` hangs after a new build, you should stop any
  running containers and repeat `make serve`.

* To run Warehouse behind a proxy set the appropriate proxy settings in the
  `Dockerfile`.

* If `sqlalchemy.exec.OperationalError` is displayed in `localhost` after
  `make serve` has been executed, shut down the Docker containers. When the
  containers have shut down, run `make serve` in one terminal window while
  running `make initdb` in a separate terminal window.

### Errors when executing `make purge`

* If `make purge` fails with a permission error, check ownership
  and permissions on `warehouse/static`. `docker compose` is spawning
  containers with docker. Generally on Linux that process is running as root.
  So when it writes files back to the file system as the static container
  does those are owned by root. So your docker daemon would be running as root,
  so your user doesn't have permission to remove the files written by the
  containers. `sudo make purge` will work.

### Errors when executing `make initdb`

* If `make initdb` fails with a timeout like:

    ```pyconsole
    urllib3.exceptions.ConnectTimeoutError: (<urllib3.connection.HTTPConnection object at 0x8beca733c3c8>, 'Connection to opensearch timed out. (connect timeout=30)')
    ```

  you might need to increase the amount of memory allocated to docker, since
  opensearch wants a lot of memory (Dustin gives warehouse ~4GB locally).
  Refer to the tip under [Running the Warehouse container and services](#running-the-warehouse-container-and-services) section for more details.

* If `make initdb` fails with an error like:

    ```shellsesion
    A fatal error has been detected by the Java Runtime Environment:
    SIGILL (0x4) at pc=0x0000f819dfc67c5c, pid=25, tid=26
    ```

    while building the `warehouse-opensearch` image, this is a known issue
    with OpenSearch in Apple M4 processors. A workaround (described in
    [this comment](https://github.com/elastic/elasticsearch/issues/118583#issuecomment-2567270484))
    is to add the following line to `dev/compose/opensearch/Dockerfile.yml` (after
    the FROM line):

    ```docker
    ENV _JAVA_OPTIONS=-XX:UseSVE=0
    ```

### "no space left on device" when using `docker compose`

`docker compose` may leave orphaned volumes during
teardown. If you run into the message "no space left on device", try
running the following command (assuming Docker >= 1.9):

```shell
docker volume rm $(docker volume ls -qf dangling=true)
```

!!! note
    This will delete orphaned volumes as well as directories that are not
    volumes in `/var/lib/docker/volumes`

(Solution found and further details available at
https://github.com/chadoe/docker-cleanup-volumes)

### `make initdb` is slow or appears to make no progress

This typically occur when Docker is not allocated enough memory to perform the
migrations. Try modifying your Docker configuration to allow more RAM for each
container, temporarily stop `make_serve` and run `make initdb` again.

### `make initdb` complains about PostgreSQL Version

You built a Warehouse install some time ago and PostgreSQL has been updated.
If you do not need the data in your databases, it might be best to just blow
away your builds + `docker` containers and start again:

```shell
make purge
docker volume rm $(docker volume ls -q --filter dangling=true)
```

### Compilation errors in non-Docker development

While Warehouse is designed to be developed in using Docker, you may
have tried to install Warehouse's requirements in your
system or virtual environment. This is discouraged as it can result in
compilation errors due to your system not including libraries
or binaries required by some of Warehouse's dependencies.

An example of such dependency is
[psycopg](https://www.psycopg.org/psycopg3/docs/basic/install.html#local-installation)
which requires PostgreSQL binaries and will fail if not present.

If there's a specific use case you think requires development outside
Docker please raise an issue in
[Warehouse's issue tracker](https://github.com/pypi/warehouse/issues).

### Disabling services locally

Some services, such as OpenSearch, consume a lot of resources when running
locally, but might not always be necessary when doing local development.

To disable these locally, you can create a `docker-compose.override.yaml`
file to override any settings in the `docker-compose.yaml` file. To
individually disable services, modify their entrypoint to do something else:

```yaml
services:
  opensearch:
    entrypoint: ["echo", "OpenSearch disabled"]
```

Note that disabling services might cause things to fail in unexpected ways.

This file is ignored in Warehouse's `.gitignore` file, so it's safe to keep
in the root of your local repo.

See the annotated file `docker-compose.override.yaml-sample` for ideas.

## Building Styles

Styles are written in the scss variant of Sass and compiled using
`webpack`. They will be automatically built when changed when
`make serve` is running.

## Running the Interactive Shell

There is an interactive shell available in Warehouse which will automatically
configure Warehouse and create a database session and make them available as
variables in the interactive shell.

To run the interactive shell, simply run:

```shell
make shell
```

The interactive shell will have the following variables defined in it:

| Variable | Description                                                                                       |
|----------|---------------------------------------------------------------------------------------------------|
| config   | The Pyramid `Configurator` object which has already been configured by Warehouse.                 |
| db       | The SQLAlchemy ORM `Session` object which has already been configured to connect to the database. |

To use the `db` object in the interactive shell, import the class you're
planning to use. For example, if I wanted to use the User object, I would
do this:

```shellsession
$ make shell
docker compose run --rm web python -m warehouse shell
Starting warehouse_redis_1 ...
...
(InteractiveConsole)
>>>
>>> from warehouse.accounts.models import User
>>> db.query(User).filter_by(username='test').all()
[User(username='test')]
```

You can also run the IPython shell as the interactive shell. To do so export
the environment variable WAREHOUSE_IPYTHON_SHELL *prior to running the*
`make build` *step*:

```shell
export WAREHOUSE_IPYTHON_SHELL=1
```

Now you will be able to run the `make shell` command to get the IPython
shell.

## Running tests and linters

!!! note
    PostgreSQL 9.4 is required because of `pgcrypto` extension

The Warehouse tests are found in the `tests/` directory and are
designed to be run using make.

To run all tests, in the root of the repository:

```shell
make tests
make static_tests
```

This will run the tests with the supported interpreter as well as all of the
additional testing that we require.

If you want to run a specific test, you can use the `T` variable:

```shell
T=tests/unit/i18n/test_filters.py make tests
```

!!! note
    By default, using the `T` variable disables testcase parallelization
    (due to runner startup time being greater than actual test time). To
    re-enable parallelization, you can pass explicit `TESTARGS`:

    ```shell
    T=tests/unit/i18n/test_filters.py TESTARGS="-n auto" make tests
    ```

    It also turns off test coverage reporting because it is almost guaranteed
    to fail and add test time overhead. To re-enable the coverage report, you
    can pass explicit `COVERAGE`:

    ```shell
    T=tests/unit/i18n/test_filters.py COVERAGE=1 make tests
    ```

You can also add arguments to the test runner by using the `TESTARGS`
variable:

```shell
TESTARGS="-vvv -x" make tests
```

This will pass the arguments `-vvv` and `-x` down to `pytest`.

This is useful in scenarios like passing a
[random seed](https://pypi.org/project/pytest-randomly/) to the test runner:

```shell
TESTARGS="--randomly-seed=1234" make tests
```

You can run linters, programs that check the code, with:

```shell
make lint
```

Warehouse uses [black](https://github.com/psf/black) for opinionated
formatting and linting. You can reformat with:

```shell
make reformat
```

## Building translations

Warehouse is translated into a number of different locales, which are stored in
the `warehouse/locale/` directory.

These translation files contain references to untranslated text in source code
and HTML templates, as well as the translations which have been submitted by
our volunteer translators.

When making changes to files with strings marked for translation, it's
necessary to update these references any time source strings are change, or the
line numbers of the source strings in the source files.

Use `make` to build the translations. For example:

```shell
make translations
```

## What next?

Look at our [open issues that are labelled "good first issue"](https://github.com/pypi/warehouse/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22), find one you
want to work on, comment on it to say you're working on it, then submit a pull
request. Use our [submitting patches](submitting-patches.md) documentation to help.

### Talk with us

You can find us via a [GitHub](https://github.com/pypi/warehouse) issue, `#pypa` or `#pypa-dev` [on
Libera](https://web.libera.chat/#pypa,#pypa-dev), the [PyPA Discord](https://discord.gg/pypa) or [Discourse](https://discuss.python.org/c/packaging/14), to ask questions or get
involved. And you can meet us in person at [packaging sprints](https://wiki.python.org/psf/PackagingSprints).

### Learn about Warehouse and packaging

Resources to help you learn Warehouse's context:

- [Roadmap](../roadmap.md)
- [blog posts, mailing list messages, and notes from our core developer meetings](https://wiki.python.org/psf/PackagingWG)
- [Warehouse codebase](../application.md)
- [the PyPA's list of presentations and articles](https://www.pypa.io/en/latest/presentations/)
- [PyPA's history of Python packaging](https://www.pypa.io/en/latest/history/)
