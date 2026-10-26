from pathlib import Path

import pytest

from kiosk.domain.cafe import Cafe
from kiosk.domain.flow import Kiosk
from kiosk.domain.loader import load_cafe, load_menu
from kiosk.domain.menu import Menu

# A fixed copy of the menu and the cafe facts, so the team can edit data/ without breaking
# the tests. tests/domain/test_data.py checks the real files.
TEST_DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def menu() -> Menu:
    return load_menu(TEST_DATA / "menu.yaml")


@pytest.fixture(scope="session")
def cafe() -> Cafe:
    return load_cafe(TEST_DATA / "cafe.yaml")


@pytest.fixture
def kiosk(menu: Menu, cafe: Cafe) -> Kiosk:
    """A kiosk with a customer on the line (the handset was lifted)."""
    k = Kiosk(menu, cafe)
    k.start_session()
    return k
