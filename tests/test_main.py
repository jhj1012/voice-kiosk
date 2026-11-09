from kiosk import __main__ as main


def test_over_usb_the_phone_listener_is_local_only(monkeypatch):
    monkeypatch.setattr(main, "laptop_addresses", lambda: ["192.168.45.113"])
    assert main.phone_listener(usb=True) == ("127.0.0.1", [])  # nothing on the Wi-Fi
    assert main.phone_listener(usb=False) == ("0.0.0.0", ["192.168.45.113"])


def test_over_usb_nothing_to_type(capsys):
    main.print_usb(8766, "http://127.0.0.1:8765")
    out = capsys.readouterr().out
    assert "https://127.0.0.1:8766" in out
    assert "주소창" not in out
