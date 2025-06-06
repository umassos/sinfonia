## Changes from original Sinfonia

- 



## Issues

1. openapi-spec-validator is nearing depreacation.

Reproduce: Starting sinfonia-tier1 `poetry run sinfonia-tier1` gives the warning:

*/Users/khainguyen/Library/Caches/pypoetry/virtualenvs/sinfonia-AWOhcxeD-py3.12/lib/python3.12/site-packages/openapi_spec_validator/schemas.py:4: UserWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html. The pkg_resources package is slated for removal as early as 2025-11-30. Refrain from using this package or pin to Setuptools<81.*

Attemps to upgrade openapi-spec-validator to newer versions are met with compilation error due to the current codebase is written in the older version syntax.
It is currently not critical, but should be considered when publishing for open source.

2. plumbum raises error on missing cli commands.

Plumbum is a Python wrapper to run CLI commands. It can raise error if a program being invoked programmatically does not exist in the CLI environment. For example, we have from plumbum.cmd import helm somewhere in the codebase. If you don't have helm installed, Plumbum will raise an error.

The fix is to simply install all used tool in this codebase.

