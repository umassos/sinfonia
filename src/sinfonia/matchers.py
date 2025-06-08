#
# Sinfonia
#
# Copyright (c) 2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#
"""Tier1 match functions

Plugin setup, additional functions can be added by external python modules
by defining 'sinfonia_tier1_matchers' setuptools entry points.
"""

from __future__ import annotations

import csv
import os
import random
import time
from operator import itemgetter
from typing import Callable, Iterator, List, Sequence, Any

from importlib_metadata import EntryPoint, entry_points

from .client_info import ClientInfo
from .cloudlets import Cloudlet
from .deployment_recipe import DeploymentRecipe

from src.domain.logger import get_default_logger


logger = get_default_logger()


CURRENT_PATH = os.path.abspath(__file__)
PROJECT_PATH = os.path.dirname(CURRENT_PATH)
LOG_PATH = f"{PROJECT_PATH}/logs"

# CARBON_INTENSITY_LOG_FILE_PATH = f"{LOG_PATH}/carbon_intensity.csv"
# CARBON_INTENSITY_CSV_HEADER = ['timestamp', 'names', 'carbon_intensity_gco2_per_kwh']

# Type definition for a Sinfonia Tier1 match function
Tier1MatchFunction = Callable[
    [ClientInfo, DeploymentRecipe, List[Cloudlet]], Iterator[Cloudlet]
]


def get_match_function_plugins() -> dict[str, EntryPoint]:
    """Returns a list of match function plugin entrypoints"""
    return {ep.name: ep for ep in entry_points(group="src.sinfonia.tier1_matchers")}


def tier1_best_match(
    match_functions: Sequence[Tier1MatchFunction],
    client_info: ClientInfo,
    deployment_recipe: DeploymentRecipe,
    cloudlets: list[Cloudlet],
) -> Iterator[Cloudlet]:
    """Generator which yields cloudlets based on selected matchers."""
    for matcher in match_functions:
        yield from matcher(client_info, deployment_recipe, cloudlets)


# ------------------ Collection of Match functions follows --------------


def match_by_network(
    client_info: ClientInfo,
    _deployment_recipe: DeploymentRecipe,
    cloudlets: list[Cloudlet],
) -> Iterator[Cloudlet]:
    """Yields any cloudlets that claim to be local.
    Also removes cloudlets that explicitly blacklist the client address
    """
    
    logger.debug("[matchers] Network matcher")

    # Used to jump the loop whenever a cloudlet can be removed from the list
    class DropCloudlet(Exception):
        pass

    for cloudlet in cloudlets[:]:        
        try:
            for network in cloudlet.rejected_clients:
                if client_info.ipaddress in network:
                    logger.debug("[matchers] Cloudlet (%s) would reject client", cloudlet.name)
                    raise DropCloudlet

            for network in cloudlet.local_networks:
                if client_info.ipaddress in network:
                    logger.debug("[matchers] Network (%s)", cloudlet.name)
                    cloudlets.remove(cloudlet)
                    yield cloudlet
                    continue

            for network in cloudlet.accepted_clients:
                if client_info.ipaddress not in network:
                    logger.debug("[matchers] Cloudlet (%s) will not accept client", cloudlet.name)
                    raise DropCloudlet
                
            yield cloudlet
            cloudlets.remove(cloudlet)
        except DropCloudlet:
            cloudlets.remove(cloudlet)


def _estimated_rtt(distance_in_km):
    """Estimated RTT based on distance and speed of light
    Only used for logging/debugging.
    """
    speed_of_light = 299792.458
    return 2 * (distance_in_km / speed_of_light)


def match_by_location(
    client_info: ClientInfo,
    _deployment_recipe: DeploymentRecipe,
    cloudlets: list[Cloudlet],
) -> Iterator[Cloudlet]:
    """Yields any geographically close cloudlets"""
    
    logger.debug("[matchers] Location matcher")
    
    if client_info.location is None:
        logger.warning(f"[matcher] client info location None")
        return

    by_distance = []

    for cloudlet in cloudlets:
        distance = cloudlet.distance_from(client_info.location)
        if distance is not None:
            by_distance.append((distance, cloudlet))

    if not by_distance:
        logger.warning(f"[matcher] by distance None")
        logger.warning(f"[matcher] client location {client_info.location}")
        return
    
    MAX_DIST_KM = 1000.0

    by_distance.sort(key=itemgetter(0))
    for distance_km, cloudlet in by_distance:
        if distance_km > MAX_DIST_KM:
            cloudlets.remove(cloudlet)
            continue
        
        logger.debug(f"[matcher] yield {cloudlet}")
        yield cloudlet


def match_random(
    _client_info: ClientInfo,
    _deployment_recipe: DeploymentRecipe,
    cloudlets: list[Cloudlet],
) -> Iterator[Cloudlet]:
    """Shuffle anything that is left and return in randomized order"""
    
    logger.debug("[matchers] Random matcher")
    
    random.shuffle(cloudlets)
    for cloudlet in cloudlets[:]:
        logger.info("random (%s)", cloudlet.name)
        cloudlets.remove(cloudlet)
        yield cloudlet


# def _append_to_csv(path: str, header: List[Any], row: List[Any]):
#     """Append a row to a CSV file"""
#     # Create logs folder if it does not exist
#     os.makedirs(LOG_PATH, exist_ok=True)

#     # If CSV file does not exist then create one and append header
#     if os.path.exists(path):
#         with open(path, mode='w', newline='') as file:
#             writer = csv.writer(file)
#             writer.writerow(header)

#     # Check that the given row has the correct number of elements
#     if len(header) != len(row):
#         raise Exception(f"Row contains incorrect number of elements. Expected {len(header)} found {len(row)}")

#     # Append row to CSV
#     with open(path, mode='a', newline='') as file:
#         writer = csv.writer(file)
#         writer.writerow(row)


# CHANGES
def match_carbon_intensity(
    _client_info: ClientInfo,
    _deployment_recipe: DeploymentRecipe,
    cloudlets: list[Cloudlet],
) -> Iterator[Cloudlet]:
    """Yields cloudlet recommendations based on lowest carbon intensity level"""
    
    logger.debug("[matchers] Carbon intensity matcher")
    # for c in cloudlets:
    #     logger.debug(f"[matchers] {c.endpoint} {c.resources['carbon_intensity_gco2_kwh']}")
    
    # Sort cloudlets by lowest carbon intensity level
    cloudlets = sorted(cloudlets, key=lambda c: c.resources['carbon_intensity_gco2_kwh'])

    # Append decision to persistent log
    # This is for debugging purposes only
    # timestamp = int(time.time())
    # names = [c.name for c in cloudlets]
    # carbon_intensity = [c.resources['carbon_intensity_gco2_kwh'] for c in cloudlets]
    # _append_to_csv(
    #     path=CARBON_INTENSITY_LOG_FILE_PATH,
    #     header=CARBON_INTENSITY_CSV_HEADER,
    #     row=[timestamp, names, carbon_intensity]
    # )

    # Yield cloudlets
    for cloudlet in cloudlets:
        cloudlets.remove(cloudlet)
        yield cloudlet
