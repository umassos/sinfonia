#
# Sinfonia
#
# run periodic tasks
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#

from typing import Dict

import pendulum
import requests
from flask_apscheduler import APScheduler
from requests.exceptions import RequestException
from yarl import URL

from .carbon import report as carbon_report
from src.domain.logger import get_default_logger


logger = get_default_logger()
scheduler = APScheduler()


def expire_cloudlets():
    cloudlets = scheduler.app.config["cloudlets"]

    expiration = pendulum.now().subtract(seconds=scheduler.app.config["CLOUDLET_EXPIRY_SECONDS"])

    for cloudlet in list(cloudlets.values()):
        if cloudlet.last_update is not None and cloudlet.last_update < expiration:
            logger.info(f"Removing stale cloudlet at {cloudlet.endpoint}")
            cloudlets.pop(cloudlet.uuid, None)


def start_expire_cloudlets_job():
    scheduler.add_job(
        func=expire_cloudlets,
        trigger="interval",
        seconds=60,
        max_instances=1,
        coalesce=True,
        id="expire_cloudlets",
        replace_existing=True,
    )


def expire_deployments():
    cluster = scheduler.app.config["K8S_CLUSTER"]
    with scheduler.app.app_context():
        cluster.expire_inactive_deployments()


def start_expire_deployments_job():
    scheduler.add_job(
        func=expire_deployments,
        trigger="interval",
        seconds=60,
        max_instances=1,
        coalesce=True,
        id="expire_deployments",
        replace_existing=True,
    )


def report_to_tier1_endpoints():
    config = scheduler.app.config

    tier2_uuid = config["UUID"]
    tier2_endpoint = URL(config["TIER2_URL"]) / "api/v1/deploy"

    cluster = config["K8S_CLUSTER"]
    resources: Dict = cluster.get_resources()
    
    # Inject carbon metrics
    if "CARBON_TRACE_TIMESTAMP" in config:
        r = carbon_report.from_simulation(
            method=config["POWER_MEASURE_METHOD"],
            energy_csv_path=config["CARBON_ENERGY_REPORT_PATH"],
            period_seconds=config["REPORT_TO_TIER1_INTERVAL_SECONDS"],
            timestamp=config["CARBON_TRACE_TIMESTAMP"],
        )
        resources.update(r.to_dict())
    
    # Inject location data
    locations = [scheduler.app.config["TIER2_GEOLOCATION"].coordinate]

    logger.debug("Reporting %s", str(resources))

    for tier1_url in config["TIER1_URLS"]:
        tier1_endpoint = URL(tier1_url) / "api/v1/cloudlets/"
        try:
            requests.post(
                str(tier1_endpoint),
                json={
                    "uuid": str(tier2_uuid),
                    "endpoint": str(tier2_endpoint),
                    "resources": resources,
                    "locations": locations,
                    },
                )
        except RequestException:
            logger.warn(f"Failed to report to {tier1_endpoint}")


def start_reporting_job():
    config = scheduler.app.config
    if not config["TIER1_URLS"] or config["TIER2_URL"] is None:
        return

    logger.info("Reporting cloudlet status to Tier1 endpoints")
    scheduler.add_job(
        func=report_to_tier1_endpoints,
        trigger="interval",
        seconds=config["REPORT_TO_TIER1_INTERVAL_SECONDS"],
        max_instances=1,
        coalesce=True,
        id="report_to_tier1",
        replace_existing=True,
    )

# CHANGES

def broadcast_carbon_trace_timestamp_to_tier2s():
    config = scheduler.app.config

    cloudlets = list(config["cloudlets"].values())
    
    curr_timestamp = config["CARBON_TRACE_TIMESTAMP"]
    for cloudlet in cloudlets:
        logger.debug(f"Setting carbon trace timestamp {curr_timestamp} on {cloudlet.name}")
        cloudlet.set_carbon_trace_timestamp(curr_timestamp)
        
    new_timestamp = curr_timestamp + config["EXPERIMENT_TICK_RATE_SECONDS"]
    config["CARBON_TRACE_TIMESTAMP"] = new_timestamp
    # TODO
    assert scheduler.app.config["CARBON_TRACE_TIMESTAMP"] == new_timestamp


# CHANGES

def start_broadcasting_job():
    config = scheduler.app.config
    if not config["CARBON_TRACE_TIMESTAMP"]:
        return
    
    logger.info("Broadcasting latest carbontrace_start to all the Tier2s")
    scheduler.add_job(
        func=broadcast_carbon_trace_timestamp_to_tier2s,
        trigger="interval",
        seconds=config["EXPERIMENT_BROADCAST_TIMESTAMP_INTERVAL_SECONDS"],
        max_instances=1,
        coalesce=True,
        id="broadcast_carbon_trace_timestamp_to_tier2s",
        replace_existing=True,
    )
