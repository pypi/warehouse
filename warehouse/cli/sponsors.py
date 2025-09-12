# SPDX-License-Identifier: Apache-2.0

from typing import cast

import click

from warehouse.cli import warehouse
from warehouse.sponsors.models import Sponsor

# SPONSORS is a copy from the sponsors variable defined in the include
# templates/includes/sponsors.html
SPONSORS_DICTS = [
    dict(
        name="Google",
        service="Object Storage and Download Analytics",
        url="https://careers.google.com/",
        image="google.png",
        activity=["Google is a visionary sponsor of the Python Software Foundation."],
        footer=True,
        psf_sponsor=True,
        infra_sponsor=True,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="Bloomberg",
        url="https://www.techatbloomberg.com/",
        image="bloomberg.png",
        activity=[
            "Bloomberg is a visionary sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="Microsoft",
        url="https://azure.microsoft.com/en-us/develop/python/",
        image="microsoft.png",
        activity=[
            "Microsoft is a visionary sponsor of the Python Software Foundation."
        ],
        footer=True,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="Facebook / Instagram",
        url="https://research.fb.com/",
        image="facebook.png",
        activity=[
            "Facebook / Instagram is a sustainability sponsor of the Python Software Foundation."  # noqa
        ],
        footer=True,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="Salesforce",
        url="https://opensource.salesforce.com/",
        image="salesforce.png",
        activity=[
            "Salesforce is a sustainability sponsor of the Python Software Foundation."
        ],
        footer=True,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="Capital One",
        url="https://www.capitalone.com/tech/",
        image="capitalone.png",
        activity=[
            "Capital One is a maintaining sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="Slack",
        url="https://slack.com",
        image="slack.png",
        activity=["Slack is a maintaining sponsor of the Python Software Foundation."],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="Corning",
        url="https://www.corning.com/",
        image="corning.png",
        activity=[
            "Corning is a maintaining sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="Latacora",
        url="https://www.latacora.com",
        image="latacora.png",
        activity=[
            "Latacora is a contributing sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="Cockroach Labs",
        url="http://www.cockroachlabs.com/",
        image="cockroach.png",
        activity=[
            "Cockroach Labs is a contributing sponsor of the Python Software Foundation."  # noqa
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="Red Hat",
        url="https://www.redhat.com/en",
        image="redhat.png",
        activity=[
            "Red Hat is a contributing sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=True,
    ),
    dict(
        name="JetBrains",
        url="https://www.jetbrains.com/pycharm",
        image="jetbrains.png",
        activity=[
            "JetBrains is a supporting sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="LinkedIn",
        url="https://www.linkedin.com",
        image="linkedin.png",
        activity=[
            "LinkedIn is a supporting sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="OpenEDG Python Institute",
        url="https://pythoninstitute.org/",
        image="openEDG.png",
        activity=[
            "OpenEDG Python Institute is a supporting sponsor of the Python Software Foundation."  # noqa
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="CircleCI",
        url="http://www.circleci.com",
        image="circleci.png",
        activity=[
            "CircleCI is a supporting sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Blackfire.io",
        url="https://www.blackfire.io/python",
        image="blackfire.png",
        activity=[
            "Blackfire.io is a supporting sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Mattermost",
        url="http://mattermost.com",
        image="mattermost.png",
        activity=["Mattermost is a partner sponsor of the Python Software Foundation."],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Tidelift",
        url="https://tidelift.com/",
        image="tidelift.png",
        activity=["Tidelift is a partner sponsor of the Python Software Foundation."],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Caktus Group",
        url="https://www.caktusgroup.com/?utm_source=psf&amp;utm_medium=sponsor&amp;utm_campaign=caktus",  # noqa
        image="caktus.png",
        activity=[
            "Caktus Group is a partner sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Reuven Lerner — Python training",
        url="https://lerner.co.il",
        image="reuven.png",
        activity=[
            "Reuven Lerner is a partner sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Saleor",
        url="http://saleor.io/",
        image="saleor.png",
        activity=["Saleor is a partner sponsor of the Python Software Foundation."],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Cuttlesoft",
        url="https://cuttlesoft.com",
        image="cuttlesoft.png",
        activity=["Cuttlesoft is a partner sponsor of the Python Software Foundation."],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="SonarSource",
        url="https://www.sonarsource.com/",
        image="sonarsource.png",
        activity=[
            "SonarSource is a partner sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Tara AI",
        url="http://tara.ai/?utm_source=PyCon&utm_medium=Sponsorship&utm_campaign=PyCon%202021",  # noqa
        image="tara.png",
        activity=["Tara AI is a partner sponsor of the Python Software Foundation."],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Elasticsearch, Inc.",
        url="https://www.elastic.co/",
        image="elastic.png",
        activity=[
            "Elasticsearch, Inc. is a partner sponsor of the Python Software Foundation."  # noqa
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Netflix",
        url="https://about.netflix.com/",
        image="netflix.png",
        activity=["Netflix is a partner sponsor of the Python Software Foundation."],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Scout APM",
        url="https://ter.li/jjv5k0",
        image="scout.png",
        activity=["Scout APM is a partner sponsor of the Python Software Foundation."],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Real Python",
        url="https://realpython.com/",
        image="realpython.png",
        activity=[
            "Real Python is a participating sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Adimian.be SPRL",
        url="https://www.adimian.com/",
        image="adimian.png",
        activity=[
            "Adimian.be SPRL is a participating sponsor of the Python Software Foundation."  # noqa
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Python Academy",
        url="https://www.python-academy.com/",
        image="pythonacademy.png",
        activity=[
            "Python Academy is a participating sponsor of the Python Software Foundation."  # noqa
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Adafruit",
        url="https://www.adafruit.com/circuitpython",
        image="adafruit.png",
        activity=[
            "Adafruit is a participating sponsor of the Python Software Foundation."
        ],
        footer=False,
        psf_sponsor=True,
        infra_sponsor=False,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Pingdom",
        service="Monitoring",
        url="https://www.pingdom.com/",
        image="pingdom.png",
        activity=[
            "PyPI's infrastructure volunteers use Pingdom to monitor and receive alerts about downtime and other issues affecting end-users."  # noqa
        ],
        footer=False,
        psf_sponsor=False,
        infra_sponsor=True,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Sentry",
        service="Error logging",
        url="https://getsentry.com/for/python",
        image="sentry.png",
        activity=[
            "The PyPI team uses Sentry to capture, record, and respond to exceptions and errors on PyPI."  # noqa
        ],
        footer=False,
        psf_sponsor=False,
        infra_sponsor=True,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="AWS",
        service="Cloud computing",
        url="https://aws.amazon.com/",
        image="aws.png",
        activity=[
            "PyPI uses AWS infrastructure to host the machines that power our services, serve DNS, host our databases, and send and monitor email.",  # noqa
        ],
        footer=False,
        psf_sponsor=False,
        infra_sponsor=True,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Datadog",
        service="Monitoring",
        url="https://www.datadoghq.com/",
        image="datadog.png",
        activity=[
            "PyPI uses Datadog to collect metrics from the applications, services, and infrastructure behind the scenes allowing for the team to measure the impact of new changes, monitor for problems, and alert when systems fail."  # noqa
        ],
        footer=False,
        psf_sponsor=False,
        infra_sponsor=True,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Fastly",
        service="CDN",
        url="https://www.fastly.com/",
        image="fastly.png",
        activity=[
            "PyPI uses Fastly's CDN to quickly serve content to end-users, allowing us to minimize our hosting infrastructure and obscure possible downtime."  # noqa
        ],
        footer=False,
        psf_sponsor=False,
        infra_sponsor=True,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="DigiCert",
        service="EV certificate",
        url="https://www.digicert.com/",
        image="digicert.png",
        activity=[
            "PyPI uses Digicert to secure communication and prove identity with an EV Certificate."  # noqa
        ],
        footer=False,
        psf_sponsor=False,
        infra_sponsor=True,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="StatusPage",
        service="Status page",
        url="https://statuspage.io",
        image="statuspage.png",
        activity=[
            "The PyPI team uses StatusPage to communicate downtime, service degradation, or maintenance windows to end-users."  # noqa
        ],
        footer=False,
        psf_sponsor=False,
        infra_sponsor=True,
        one_time=False,
        sidebar=False,
    ),
    dict(
        name="Mozilla",
        url="https://www.mozilla.org",
        image="mozilla.png",
        activity=[
            "In late 2017 the Python Software Foundation was awarded a Mozilla Open Source Support (MOSS) award.",  # noqa
            "This award was used to move PyPI from its legacy codebase and deploy Warehouse - the new codebase powering PyPI.",  # noqa
        ],
        footer=False,
        psf_sponsor=False,
        infra_sponsor=False,
        one_time=True,
        sidebar=False,
    ),
    dict(
        name="Open Technology Fund",
        url="https://www.opentech.fund",
        image="otf.png",
        activity=[
            "In 2019 the Python Software Foundation was awarded a contract through the OTF Core Infrastructure Fund.",  # noqa
            "This contract included an audit and improvements to the accessibility of PyPI, internationalization and translations for PyPI user interface, and security features including two-factor authentication and API tokens for uploads.",  # noqa
        ],
        footer=False,
        psf_sponsor=False,
        infra_sponsor=False,
        one_time=True,
        sidebar=False,
    ),
]


WHITE_BASE_URL = "https://pypi.org/static/images/sponsors/white/"
BLACK_BASE_URL = "https://pypi.org/static/images/sponsors/color/"


@warehouse.group()
def sponsors():
    """
    Manage operations on top of sponsors.
    """


@sponsors.command()
@click.pass_obj
def populate_db(config):
    """
    Sync the Warehouse database with initial sponsors list.
    Once this command is executed once, you shouldn't need to run
    it again.
    """
    # Imported here because we don't want to trigger an import from anything
    # but warehouse.cli at the module scope.
    from warehouse.db import Session

    session = Session(bind=config.registry["sqlalchemy.engine"])

    for data in SPONSORS_DICTS:
        name = data["name"]
        sponsor = session.query(Sponsor).filter_by(name=name).one_or_none()
        if sponsor:
            print(f"Skipping {name} sponsor because it already exists.")
            continue

        params = data.copy()
        img = params.pop("image")
        params["is_active"] = True
        params["link_url"] = params.pop("url")
        params["activity_markdown"] = "\n\n".join(
            cast(list, params.pop("activity", []))
        ).strip()
        params["color_logo_url"] = BLACK_BASE_URL + str(img)
        if params["footer"] or params["infra_sponsor"]:
            params["white_logo_url"] = WHITE_BASE_URL + str(img)

        sponsor = Sponsor(**params)
        try:
            session.add(sponsor)
            session.commit()
            print(f"{name} sponsor created with success.")
        except Exception as e:
            session.rollback()
            print(f"Error while creating {name} sponsor:")
            print(f"\t{e}")
