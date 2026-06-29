from pathlib import Path

import pytest

from sialytics.security import NavigationDenied, NavigationPolicy, safe_spreadsheet_text


def test_policy_uses_exact_institutional_hosts() -> None:
    policy = NavigationPolicy({"auth.unal.edu.co"})
    policy.assert_navigation_url("https://sia.unal.edu.co/ServiciosApp")
    policy.assert_navigation_url("https://autenticasia.unal.edu.co/login")
    policy.assert_navigation_url("https://auth.unal.edu.co/login")
    with pytest.raises(NavigationDenied):
        policy.assert_navigation_url("https://otro.unal.edu.co/")
    with pytest.raises(NavigationDenied):
        policy.assert_navigation_url("http://sia.unal.edu.co/")


@pytest.mark.parametrize("host", ["evil.example", "*.unal.edu.co", "https://auth.unal.edu.co"])
def test_policy_rejects_non_exact_or_non_institutional_hosts(host: str) -> None:
    with pytest.raises(ValueError):
        NavigationPolicy({host})


def test_academic_data_must_come_from_exact_sia_host() -> None:
    NavigationPolicy.assert_academic_source("https://sia.unal.edu.co/page")
    with pytest.raises(NavigationDenied):
        NavigationPolicy.assert_academic_source("https://auth.unal.edu.co/page")
    with pytest.raises(NavigationDenied):
        NavigationPolicy.assert_academic_source("https://sia.unal.edu.co.evil.example/page")


def test_spreadsheet_formula_prefixes_are_neutralized(tmp_path: Path) -> None:
    assert safe_spreadsheet_text("=1+1") == "'=1+1"
    assert safe_spreadsheet_text("  =1+1") == "'  =1+1"
    assert safe_spreadsheet_text("texto") == "texto"
