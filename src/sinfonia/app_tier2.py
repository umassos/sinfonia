#
# Sinfonia
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from __future__ import annotations

import time
import socket
from pathlib import Path
from uuid import uuid4

import connexion
import typer
from attrs import define
from connexion.resolver import MethodViewResolver
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.serving import get_interface_ip
from yarl import URL
from zeroconf import ServiceInfo, Zeroconf

from . import  daemon_registry
from .carbon.simulation import carbon_trace
from .carbon.types import EnergyReportMethodType
from .app_common import (
    OptionalBool,
    OptionalPath,
    OptionalStr,
    StrList,
    recipes_option,
    version_option,
)
from .cluster import Cluster
from .daemons import energy_report
from .deployment_repository import DeploymentRepository
from .jobs import scheduler, start_expire_deployments_job, start_reporting_job
from .openapi import load_spec
from .geo_location import GeoLocation

from src.domain.logger import get_default_logger
from src.lib.time import TimeUnit


logger = get_default_logger()


class Tier2DefaultConfig:
    # Sinfonia
    TIER1_URLS = ["http://192.168.245.26:5000"]
    TIER2_URL = "http://192.168.245.26:5001"
    TIER2_LATITUDE = 30.332184
    TIER2_LONGITUDE = -81.655647
    TIER2_ZONE = "US-FLA-JEA"
    TRACE_GITHUB_REPO_URL = "https://github.com/k2nt/k2nt.github.io/blob/main/projects/sinfonia/carbon_traces"
    RECIPES: str | Path | URL = "RECIPES"
    PROMETHEUS: str = "http://10.43.247.5:9090"
        
    # CHANGES

    # Carbon
    CARBON_ENERGY_REPORT_PATH = './carbon-data/energy.csv'
    CARBON_ENERGY_REPORT_RESET_INTERVAL_SECONDS = TimeUnit.DAY
        
    # Experiment
    REPORT_TO_TIER1_INTERVAL_SECONDS = 15
    OBELIX_NODE_NAME = "obelix32"
    POWER_MEASURE_METHOD = EnergyReportMethodType.RAPL
    

def tier2_app_factory(**args) -> connexion.FlaskApp:
    """Sinfonia Tier 2 API server"""
    app = connexion.FlaskApp(__name__, specification_dir="openapi/")

    # load configurations
    
    flask_app = app.app
    flask_app.config.from_object(Tier2DefaultConfig)
    flask_app.config.from_envvar("SINFONIA_SETTINGS", silent=True)
    flask_app.config.from_prefixed_env(prefix="SINFONIA")
    flask_app.config.from_prefixed_env(prefix="EXPERIMENT")
    cmdargs = {k.upper(): v for k, v in args.items() if v}
    flask_app.config.from_mapping(cmdargs)
    
    # tier1 url
    
    tier1_url = flask_app.config.get("TIER1_URL")
    if tier1_url is not None:
        flask_app.config["TIER1_URLS"] = [tier1_url]

    # geolocation

    tier2_latitude = flask_app.config.get("TIER2_LATITUDE", None)
    tier2_longitude = flask_app.config.get("TIER2_LONGITUDE", None)
    
    if tier2_latitude is None or tier2_longitude is None:
        raise ValueError("missing tier2 geolocation data")
        
    flask_app.config["TIER2_GEOLOCATION"] = GeoLocation(
        flask_app.config.get("TIER2_LATITUDE", None), 
        flask_app.config.get("TIER2_LONGITUDE", None)
        )
    
    # zone / carbon trace
    
    tier2_zone = flask_app.config.get("TIER2_ZONE")
    if tier2_zone is None:
        raise ValueError("missing tier2 zone data")
    
    tier2_repo_url = flask_app.config.get("TRACE_GITHUB_REPO_URL")
    if tier2_repo_url is None:
        raise ValueError("missing carbon trace repo url")
    
    carbon_trace.fetch_from_github(tier2_zone, tier2_repo_url)
    
    # uuid
        
    flask_app.config["UUID"] = uuid4()
    flask_app.config["deployment_repository"] = DeploymentRepository(
        flask_app.config["RECIPES"]
    )

    # connect to local kubernetes cluster
    
    cluster = Cluster.connect(
        flask_app.config.get("KUBECONFIG", ""), flask_app.config.get("KUBECONTEXT", "")
    )
    cluster.prometheus_url = (
        URL(flask_app.config["PROMETHEUS"]) / "api" / "v1" / "query"
    )
    flask_app.config["K8S_CLUSTER"] = cluster

    # start background jobs to expire deployments and report to tier1
    
    scheduler.init_app(flask_app)
    scheduler.start()
    start_expire_deployments_job()
    start_reporting_job()
    
    # start daemons
    
    # CHANGES

    logger.info(f"Starting carbon energy daemon and creating energy report at {flask_app.config['CARBON_ENERGY_REPORT_PATH']} ...")
    daemon_registry.register(
        energy_report, 
        {
            "path": flask_app.config["CARBON_ENERGY_REPORT_PATH"],
            "reset_interval_seconds": flask_app.config["CARBON_ENERGY_REPORT_RESET_INTERVAL_SECONDS"],
        }
    )
    daemon_registry.start()

    # handle running behind reverse proxy (should this be made configurable?)
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app)

    # add tier 2 api
    
    app.add_api(
        load_spec(app.specification_dir / "sinfonia_tier2.yaml"),
        resolver=MethodViewResolver("src.sinfonia.api_tier2"),
        validate_responses=True,
    )

    return app


@define
class ZeroconfMDNS:
    """Wrapper helping with zeroconf service registration"""

    zeroconf: Zeroconf | None = None

    def announce(self, port: int) -> None:
        """Try to announce our service on IPv4 and IPv6 on all interfaces"""
        if self.zeroconf is not None:
            self.withdraw()

        # werkzeug uses this function to figure out the ip address of the interface
        # that handles the default route. This should work as long as we don't
        # happen to have a secondary interface on the 10.0.0.0/8 network, I think.
        # either way, this seems to be about the best we can do for now because
        # when we just give a list of all known local addresses, it seems like
        # only the last IPv4 and IPv6 addresses end up being resolvable, and
        # these tend to be local-only docker or kvm network addresses on my system.
        address = get_interface_ip(socket.AF_INET)

        info = ServiceInfo(
            "_sinfonia._tcp.local.",
            "cloudlet._sinfonia._tcp.local.",
            parsed_addresses=[address],
            port=port,
            properties=dict(path="/"),
        )
        self.zeroconf = Zeroconf()
        self.zeroconf.register_service(info, allow_name_change=True)

    def withdraw(self) -> None:
        """Withdraw service registration"""
        if self.zeroconf is not None:
            self.zeroconf.unregister_all_services()
            self.zeroconf.close()
            self.zeroconf = None


cli = typer.Typer()


@cli.command()
def tier2_server(
    version: OptionalBool = version_option,
    port: int = typer.Option(5001, help="Port to listen for requests"),
    recipes: OptionalStr = recipes_option,
    kubeconfig: OptionalPath = typer.Option(
        None,
        help="Path to kubeconfig file",
        show_default=False,
        exists=True,
        dir_okay=False,
        resolve_path=True,
        rich_help_panel="Kubernetes cluster config",
    ),
    kubecontext: str = typer.Option(
        "",
        help="Name of kubeconfig context to use",
        show_default=False,
        rich_help_panel="Kubernetes cluster config",
    ),
    prometheus: OptionalStr = typer.Option(
        None,
        metavar="URL",
        help="Prometheus endpoint",
        show_default=False,
        rich_help_panel="Kubernetes cluster config",
    ),
    tier1_urls: StrList = typer.Option(
        [],
        "--tier1-url",
        metavar="URL",
        help="Base URL of Tier 1 instances to report to (may be repeated)",
        rich_help_panel="Sinfonia Tier1 reporting",
    ),
    tier2_url: OptionalStr = typer.Option(
        None,
        metavar="URL",
        help="Base URL of this Tier 2 instance",
        show_default=False,
        rich_help_panel="Sinfonia Tier1 reporting",
    ),
    zeroconf: bool = typer.Option(
        False,
        help="Announce cloudlet on local network(s) with zeroconf mdns",
    ),
):
    """Run Sinfonia TIer2 with Flask's builtin server (for development)"""
    app = tier2_app_factory(
        recipes=recipes,
        kubeconfig=kubeconfig,
        kubecontext=kubecontext,
        prometheus=prometheus,
        tier1_urls=tier1_urls,
        tier2_url=tier2_url,
    )

    # run application, optionally announcing availability with MDNS
    zeroconf_mdns = ZeroconfMDNS()
    if zeroconf:
        zeroconf_mdns.announce(port)
    try:
        app.run(port=port)
    except KeyboardInterrupt:
        pass
    finally:
        zeroconf_mdns.withdraw()
