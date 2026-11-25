# SPDX-License-Identifier: Apache-2.0
import pytest

from ttvga import devtools


@pytest.fixture
def dev_tools() -> devtools.DevTools:
    """The dev-tools paths. Checks nothing: each sim test calls `require` with the tools it uses."""
    return devtools.paths()
