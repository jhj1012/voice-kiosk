"""The phone mode's certificate, made in a temporary folder."""

from cryptography import x509

from kiosk.server.certificate import ensure_certificate, laptop_addresses


def addresses_in(path) -> set[str]:
    cert = x509.load_pem_x509_certificate(path.read_bytes())
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return {str(ip) for ip in names.get_values_for_type(x509.IPAddress)}


def test_made_once_for_the_laptops_addresses(tmp_path):
    files = ensure_certificate(tmp_path, ["192.168.43.12"])
    assert files.key.exists()
    assert addresses_in(files.cert) == {"127.0.0.1", "192.168.43.12"}
    made = files.cert.read_bytes()
    assert ensure_certificate(tmp_path, ["192.168.43.12"]).cert.read_bytes() == made  # reused
    assert ensure_certificate(tmp_path, []).cert.read_bytes() == made


def test_made_again_for_a_new_address(tmp_path):
    ensure_certificate(tmp_path, ["192.168.43.12"])
    files = ensure_certificate(tmp_path, ["192.168.43.77"])
    assert "192.168.43.77" in addresses_in(files.cert)


def test_a_broken_file_is_replaced(tmp_path):
    files = ensure_certificate(tmp_path, ["10.0.0.5"])
    files.cert.write_text("not a certificate")
    assert addresses_in(ensure_certificate(tmp_path, ["10.0.0.5"]).cert) >= {"10.0.0.5"}


def test_laptop_addresses_leave_out_loopback():
    assert all(not a.startswith("127.") for a in laptop_addresses())
