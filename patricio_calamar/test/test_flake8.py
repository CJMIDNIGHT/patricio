import pytest
from ament_flake8.main import main_with_errors
@pytest.mark.flake8
def test_flake8():
    rc, errors = main_with_errors(argv=[])
    assert rc == 0, errors
