"""Tests for providers/__init__.py — registry."""

import pytest

from adata.providers import get_provider, list_providers
from adata.providers.base import BaseProvider


class TestProviderRegistry:
    def test_list_providers_returns_list(self):
        providers = list_providers()
        assert isinstance(providers, list)
        assert len(providers) > 0

    def test_rqdatac_registered(self):
        assert "rqdatac" in list_providers()

    def test_get_provider_rqdatac(self):
        p = get_provider("rqdatac")
        assert isinstance(p, BaseProvider)
        assert p.name == "rqdatac"

    def test_get_provider_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent_provider")

    def test_all_providers_are_base_provider(self):
        for name in list_providers():
            p = get_provider(name)
            assert isinstance(p, BaseProvider)
            assert p.name == name

    def test_all_providers_have_supported_types(self):
        for name in list_providers():
            p = get_provider(name)
            assert len(p.supported_asset_types) > 0

    def test_supports_method(self):
        for name in list_providers():
            p = get_provider(name)
            for asset_type in p.supported_asset_types:
                assert p.supports(asset_type) is True
            assert p.supports("nonexistent_type") is False
