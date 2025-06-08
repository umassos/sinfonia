#
# Sinfonia
#
# deploy helm charts to a cloudlet kubernetes cluster for edge-native applications
#
# Copyright (c) 2021-2022 Carnegie Mellon University
#
# SPDX-License-Identifier: MIT
#
from concurrent.futures import CancelledError

from connexion import NoContent
from connexion.exceptions import ProblemException
from flask import current_app, request
from flask.views import MethodView
from pydantic import BaseModel, validator

from src.domain.logger import get_default_logger
from src.sinfonia.carbon import report as carbon_report


logger = get_default_logger()

# CHANGES

class CarbonGet(BaseModel):
    carbon_trace_timestamp: int = 0
    
    @validator('carbon_trace_timestamp')
    def _check_non_negative(cls, v):
        if v < 0:
            raise ValueError('must be non-negative')
        return v

# CHANGES

class CarbonView(MethodView):
    def search(self):        
        config = current_app.config
        
        if 'CARBON_TRACE_TIMESTAMP' not in config:
            raise ProblemException(400, f"carbon trace timestamp not yet recorded")
        
        r = carbon_report.from_simulation(
            node_name=config["OBELIX_NODE_NAME"],
            method=config["POWER_MEASURE_METHOD"],
            t_sec=config["REPORT_TO_TIER1_INTERVAL_SECONDS"],
            timestamp=config["CARBON_TRACE_TIMESTAMP"],
            )
        logger.debug(f"[CarbonView] {config['OBELIX_NODE_NAME']} -- ts {config['CARBON_TRACE_TIMESTAMP']} -- ci {r.carbon_intensity_gco2_kwh}")
        return r


# CHANGES

class CarbonTraceTimestampView(MethodView):
    def post(self):
        try:
            req = CarbonGet(**request.args)
        except ValueError as e:
            raise ProblemException(400, "Error", f"Failed to parse request {e!r}")
        
        current_app.config['CARBON_TRACE_TIMESTAMP'] = req.carbon_trace_timestamp
        return NoContent, 200

# CHANGES

class LivezView(MethodView):
    def search(self):
        return NoContent, 200
    
# CHANGES

class ReadyzView(MethodView):
    def search(self):
        return NoContent, 200
    
# CHANGES
    
class ResuView(MethodView):
    """Resource Utilization"""
    def search(self):
        return current_app.config['K8S_CLUSTER'].get_resources()


class DeployView(MethodView):
    def post(self, uuid, application_key):
        config = current_app.config
        cluster = config["K8S_CLUSTER"]
        default_endpoint = config["TIER2_URL"]
        
        deployment = cluster.get(uuid, application_key, create=True)
        try:
            deployment.deploy()
        except (CancelledError, TimeoutError) as e:
            raise ProblemException(400, "Error", f"Failed to deploy {e!r}")
        except Exception as e:
            raise ProblemException(500, "Error", f"Error occured {e!r}")

        d = deployment.asdict(default_endpoint=default_endpoint)
        logger.debug(f"[DeployView] POST {d}")

        return [d]

    def get(self, uuid, application_key):
        cluster = current_app.config["K8S_CLUSTER"]
        deployment = cluster.get(uuid, application_key)
        if deployment is None:
            raise ProblemException(
                404, "Not Found", title="Unable to find existing deployment"
            )
        return deployment.asdict()

    def delete(self, uuid, application_key):
        cluster = current_app.config["K8S_CLUSTER"]
        
        deployment = cluster.get(uuid, application_key)
        if deployment is not None:
            try:
                deployment.expire()
            except Exception as e:
                raise ProblemException(500, "Error", f"Error occured {e!r}")
        
        return NoContent, 204
