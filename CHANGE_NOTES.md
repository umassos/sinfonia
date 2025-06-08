# CHANGELOG

Last commit reference from CMU: 79b26ce

Last commit reference from CarbonEdge: TBD

## Experiment design

This is to recap on the experiments were designed on top of Sinfonia.



## Changes from original Sinfonia

This section lists major changes from the original Sinfonia codebase.

### Recipes

Added Sinfonia recipes to deploy loadtest applications.

The matrix multiplication loadtest recipes are:
1. RECIPES/00000000-0000-0000-0000-000000000111.yaml
1. RECIPES/00000000-0000-0000-0000-000000000126.yaml
1. RECIPES/00000000-0000-0000-0000-000000030126.yaml
1. RECIPES/00000000-0000-0000-0000-000000030127.yaml
1. RECIPES/00000000-0000-0000-0000-000000030128.yaml
1. RECIPES/00000000-0000-0000-0000-000000030130.yaml
1. RECIPES/00000000-0000-0000-0000-000000030139.yaml

In addition, the NVIDIA Triton Resnet50 loadtest recipes are:
1. RECIPES/00000000-0000-0000-0000-100000000000.yaml

### Helm chart / trace repo

Sinfonia recipes are essentially wrappers around a Helm chart. We host our own Helm repo to deploy test applications. Right now the Helm repo is located on my personal Github repo at https://github.com/k2nt/sinfonia-helm-repo

In addition, the Github repo also serves as the carbon trace repo. Loadtest deployments, per their configuration, will download the corresponding carbon traces from the Github repo for carbon trace replay.

### Matchers

Added carbon intensity matcher. The logic is simply to route requests to lowest carbon intensity region.

Main logic function at src/sinfonia/matchers:match_carbon_intensity (ln 190)

Registered to Poetry as a package at pyproject.toml (ln 90)

### Dependencies:

The original Sinfonia codebase was developed 3 years ago, with some dependencies being older than that. I took the liberty to upgrade dependencies to the latest (as of writing) possible versions for future compatability. After the upgrade, the codebase is still able to be compiled and all functionalities are preserved and tested.

Sinfonia uses Poetry to manage dependencies. All dependencies and version control are listed in the given pyproject.toml file.

Tests are performed with Python 3.12.

### Logging

Added structured and colored logging for better visualization. 

Logger logic at src/logger.

Imports and uses added throughout codebase.

### Energy metrics

Added daemon to continuously generate RAPL sampling.

Daemon registry logic to manage daemon activities at src/sinfonia/daemon_registry.py

Energy daemon and future daemon logic at src/sinfonia/daemons.py

Registering energy daemon at tier2 at src/sinfonia/app_tier2.py (ln 142 - 150)

### Global clock time sync

For sake of experiment, we need a way to simulate time for the carbon replay. The clock starts from the carbon trace's first timestamp, or some pre-customized timestamp. For every second, the clock ticks for some pre-cutomized amount (e.g. 1 real-world second <-> 12 simulated seconds). 

Main logic at src/sinfonia/cloudlets.py:set_carbon_trace_timestamp (ln 339 - ln 352)

Broadcasting clock value to Tier-2s at src/sinfonia/jobs.py:broadcast_carbon_trace_timestamp_to_tier2s (ln 126 - ln 139)

Start broadcasting job from Tier-1 at src/sinfonia/app_tier1.py (ln 129)

API endpoint on Tier-2 to update its carbon trace timestamp at src/sinfonia/api_tier2.py:CarbonTraceTimestampView (ln 56 - ln 64)

### Loadtest

We have a loadtest repo independent of the repository. The loadtest is acts as Tier-3, the application edge node.

## Issues

These are issues I noticed.

### Dependencies

#### 1. openapi-spec-validator is nearing depreacation.

Reproduce: Starting sinfonia-tier1 `poetry run sinfonia-tier1` gives the warning:

*/Users/khainguyen/Library/Caches/pypoetry/virtualenvs/sinfonia-AWOhcxeD-py3.12/lib/python3.12/site-packages/openapi_spec_validator/schemas.py:4: UserWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html. The pkg_resources package is slated for removal as early as 2025-11-30. Refrain from using this package or pin to Setuptools<81.*

Attemps to upgrade openapi-spec-validator to newer versions are met with compilation error due to the current codebase is written in the older version syntax.
It is currently not critical, but should be considered when publishing for open source.

#### 2. Plumbum raises error on missing cli commands.

Plumbum is a Python wrapper to run CLI commands. It can raise error if a program being invoked programmatically does not exist in the CLI environment. For example, we have from plumbum.cmd import helm somewhere in the codebase. If you don't have helm installed, Plumbum will raise an error.

The fix is to simply install all used tool in this codebase.

## To dos

These are the things I think we should do before open sourcing Carbon Edge.

### Merge loadtest into this codebase

Currently loadtest is in a different repo, being built on top of the Sinfonia-Tier3 repo which itself was separated from Sinfonia by CMU themselves. Since our main contribution is the matcher function and experiment results, this is a core Carbon Edge feature and should be added to the official Carbon Edge repo.

### Decide which loadtest to present

We have two loadtest applications through two CarbonEdge paper submissions. The one for the during the first submission (for SIGMETRICS) was a simple matrix multiplication application. The one during the second submission (for HPDC) was on a Resnet50 model served on NVIDIA Triton.

### Make running experiments easier

Sinfonia was designed to run on Kubernetes and has many external hooks to configure before it can be started (e.g. Prometheus/Grafana, Helm chart, etc.). We added our own hooks for CarbonEdge (e.g. RAPL daemon, time sync between Tier-1 and Tier-2, carbon trace repo). 

We should have an easier way for a new user (think CMU or other developers/researchers) to run experiments on CarbonEdge. 

### Clean up debugging loggings

The codebase is littered with debugging logging during development, we should reconsider which information should we print out.
