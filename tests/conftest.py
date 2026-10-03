import pytest

from kiosk.config import DATA_DIR
from kiosk.domain.cafe import Cafe
from kiosk.domain.flow import Kiosk
from kiosk.domain.loader import load_cafe, load_menu
from kiosk.domain.menu import Menu


@pytest.fixture(scope="session")
def menu() -> Menu:
    return load_menu(DATA_DIR / "menu.yaml")


@pytest.fixture(scope="session")
def cafe() -> Cafe:
    return load_cafe(DATA_DIR / "cafe.yaml")


@pytest.fixture
def kiosk(menu: Menu, cafe: Cafe) -> Kiosk:
    """A kiosk with a customer on the line (the handset was lifted)."""
    k = Kiosk(menu, cafe)
    k.start_session()
    return k
