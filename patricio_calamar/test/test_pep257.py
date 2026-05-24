import pytest
from ament_pep257.main import main
@pytest.mark.pep257
def test_pep257():
    rc = main(argv=[])
    assert rc == 0
