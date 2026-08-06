from __future__ import annotations

import pytest

from core.kernel.container import Container, ContainerError


class _Interface:
    pass


class _Impl(_Interface):
    pass


def test_register_instance_resolves_same_instance() -> None:
    container = Container()
    instance = _Impl()
    container.register_instance(_Interface, instance)

    assert container.resolve(_Interface) is instance


def test_register_factory_singleton_resolves_same_instance() -> None:
    container = Container()
    container.register_factory(_Interface, _Impl)

    first = container.resolve(_Interface)
    second = container.resolve(_Interface)

    assert first is second


def test_register_factory_non_singleton_resolves_new_instance() -> None:
    container = Container()
    container.register_factory(_Interface, _Impl, singleton=False)

    first = container.resolve(_Interface)
    second = container.resolve(_Interface)

    assert first is not second


def test_resolve_unregistered_raises() -> None:
    container = Container()

    with pytest.raises(ContainerError):
        container.resolve(_Interface)
