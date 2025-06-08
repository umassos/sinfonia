#
# Sinfonia
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

import connexion
import typer
from connexion.resolver import MethodViewResolver
from flask_executor import Executor
from geolite2 import geolite2
from rich import print
from werkzeug.middleware.proxy_fix import ProxyFix
from yarl import URL

from .app_common import (
    OptionalBool,
    OptionalPath,
    OptionalStr,
    StrList,
    port_option,
    recipes_option,
    version_option,
)
from .cloudlets import Cloudlet
from .cloudlets import load as cloudlets_load
from .deployment_repository import DeploymentRepository
from .jobs import scheduler, start_expire_cloudlets_job, start_broadcasting_job
from .matchers import Tier1MatchFunction, get_match_function_plugins
from .openapi import load_spec

from src.domain.logger import get_default_logger


logger = get_default_logger()


class Tier1DefaultConfig:
    # MATCHERS serve as filter
    # Default is network -> location -> random -> cloudlet recommendations
    # We are setting match carbon as the single filter
    # MATCHERS declaration can be found in poetry's pyproject.toml
    # MATCHERS: list[str] = ["network", "location", "random"]
    MATCHERS: list[str] = ["network", "location", "carbon-intensity"] # "carbon-intensity"
    CLOUDLETS: str | Path | None = None
    RECIPES: str | Path | URL = "RECIPES"    
    CLOUDLET_EXPIRY_SECONDS = 60
    EXPERIMENT_BROADCAST_TIMESTAMP_INTERVAL_SECONDS = 1
    EXPERIMENT_TICK_RATE_SECONDS = 12
    CARBON_TRACE_TIMESTAMP = 1672546320  # 1672549200 - 12 * 240
    # 2023-01-03 00:00:00 1672704000 / 1672704000 - (12*180) = 1672701840
    
    # 2023-07-03 00:00:00 1688342400 / 1688342400 - (12*180) = 1688340240


def load_cloudlets_conf(cloudlets_conf: str | Path | None) -> dict[UUID, Cloudlet]:
    """read cloudlets.yaml configuration file to preseed Tier2 cloudlets

    this depends on flask_app.config["geolite2_reader"]
    """
    if cloudlets_conf is None:
        return {}

    with Path(cloudlets_conf).open() as stream:
        cloudlets = cloudlets_load(stream)

    return {cloudlet.uuid: cloudlet for cloudlet in cloudlets}


def list_match_functions(value):
    if value:
        print("Available tier1 match functions:")
        matchers = get_match_function_plugins().keys()
        print(sorted(matchers))
        raise typer.Exit()


def load_match_functions(matchers: list[str]) -> list[Tier1MatchFunction]:
    """load pluggable functions to select Tier2 candidates"""
    try:
        tier1_matchers = get_match_function_plugins()
        match_functions = [tier1_matchers[matcher].load() for matcher in matchers]
        logger.info(f"Loaded match functions {matchers}")
    except KeyError as e:
        sys.exit(f"Error: Match function '{e.args[0]}' not found")
    return match_functions


def wsgi_app_factory(**args) -> connexion.FlaskApp:
    """Sinfonia Tier 1 API server"""
    app = connexion.FlaskApp(__name__, specification_dir="openapi/")

    flask_app = app.app
    flask_app.config.from_object(Tier1DefaultConfig)
    flask_app.config.from_envvar("SINFONIA_SETTINGS", silent=True)
    flask_app.config.from_prefixed_env(prefix="SINFONIA")

    cmdargs = {k.upper(): v for k, v in args.items() if v}
    flask_app.config.from_mapping(cmdargs)

    flask_app.config["executor"] = Executor(flask_app)
    flask_app.config["geolite2_reader"] = geolite2.reader()

    with flask_app.app_context():
        flask_app.config["cloudlets"] = load_cloudlets_conf(
            flask_app.config.get("CLOUDLETS")
        )
    flask_app.config["deployment_repository"] = DeploymentRepository(
        flask_app.config["RECIPES"]
    )
    flask_app.config["match_functions"] = load_match_functions(
        flask_app.config["MATCHERS"]
    )

    # start background job to expire Tier2 cloudlets that are no longer reporting
    scheduler.init_app(flask_app)
    scheduler.start()
    start_expire_cloudlets_job()

    # CHANGES
    start_broadcasting_job()

    # handle running behind reverse proxy (should this be made configurable?)
    flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app)

    # add Tier1 APIs
    app.add_api(
        load_spec(app.specification_dir / "sinfonia_tier1.yaml"),
        resolver=MethodViewResolver("src.sinfonia.api_tier1"),
        validate_responses=True,
    )

    @app.route("/")
    def index():
        return ""

    return app


cli = typer.Typer()


@cli.command()
def tier1_server(
    version: OptionalBool = version_option,
    port: int = port_option,
    cloudlets: OptionalPath = typer.Option(
        None,
        help="Read YAML file containing known Tier2 cloudlets",
        show_default=False,
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    recipes: OptionalStr = recipes_option,
    matchers: StrList = typer.Option(
        [],
        "--match",
        "-m",
        help="Select Tier2 best match functions [default: network, location, random]",
    ),
    list_matchers: OptionalBool = typer.Option(
        None,
        "--list-matchers",
        callback=list_match_functions,
        is_eager=True,
        help="Show available best match functions",
    ),
):
    """Run Sinfonia Tier1 with Flask's builtin server (for development)"""
    app = wsgi_app_factory(cloudlets=cloudlets, recipes=recipes, matchers=matchers)
    app.run(port=port)
