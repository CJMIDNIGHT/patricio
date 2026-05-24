# Copyright 2026 Patricio
# Licensed under the Apache License, Version 2.0

from ament_pep257.main import main
import pytest


@pytest.mark.pep257
@pytest.mark.linter
def test_pep257():
    rc = main(argv=['.', 'patricio_voz'])
    assert rc == 0, 'Found code style errors / warnings'
