"""Service registry and dependency injection container.

Provides centralized service lookup with lazy factory support,
health tracking, and ordered shutdown. Thread-safe for concurrent
access from multiple modules.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

_default_registry: ServiceRegistry | None = None


class ServiceRegistry:
    """Central service registry / dependency injection container.

    Services can be registered as pre-built instances or as factory
    callables that are invoked lazily on first access. Health status
    is tracked per-service for monitoring.

    Usage::

        registry = get_registry()
        registry.register("packet_store", packet_store)
        registry.register_factory("analyzer", lambda: Analyzer())
        store = registry.get("packet_store")
    """

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}
        self._factories: dict[str, Callable[[], Any]] = {}
        self._lock = threading.Lock()
        self._health: dict[str, str] = {}
        self._registration_order: list[str] = []

    def register(
        self, name: str, service: Any, lazy: bool = False
    ) -> None:
        """Register a service instance or factory.

        Args:
            name: Unique service name.
            service: Either a ready instance (lazy=False) or a
                zero-argument callable factory (lazy=True).
            lazy: If True, *service* is treated as a factory that will
                be called on first ``get``.
        """
        with self._lock:
            if lazy:
                self._factories[name] = service
                self._health[name] = "healthy"
                logger.debug("Registered lazy factory: %s", name)
            else:
                self._services[name] = service
                self._health[name] = "healthy"
                logger.debug("Registered service: %s", name)
            if name not in self._registration_order:
                self._registration_order.append(name)

    def register_factory(
        self, name: str, factory: Callable[[], Any]
    ) -> None:
        """Register a lazy factory callable.

        Args:
            name: Unique service name.
            factory: Zero-argument callable that creates the service.
        """
        self.register(name, factory, lazy=True)

    def get(self, name: str) -> Any:
        """Retrieve a service by name.

        If the service was registered as a factory and hasn't been
        instantiated yet, it will be created on first access.

        Args:
            name: Service name.

        Returns:
            The service instance.

        Raises:
            KeyError: If no service or factory is registered under *name*.
        """
        with self._lock:
            if name in self._services:
                return self._services[name]
            if name in self._factories:
                factory = self._factories[name]
                instance = self._create_instance(factory)
                self._services[name] = instance
                del self._factories[name]
                return instance
        raise KeyError(f"Service not registered: {name!r}")

    def get_optional(self, name: str, default: Any = None) -> Any:
        """Retrieve a service or return a default if not found.

        Args:
            name: Service name.
            default: Value to return when the service is absent.

        Returns:
            The service instance, or *default*.
        """
        try:
            return self.get(name)
        except KeyError:
            return default

    def has(self, name: str) -> bool:
        """Check whether a service or factory is registered.

        Args:
            name: Service name.
        """
        with self._lock:
            return name in self._services or name in self._factories

    def remove(self, name: str) -> bool:
        """Remove a registered service.

        Args:
            name: Service name.

        Returns:
            True if the service was found and removed, False otherwise.
        """
        with self._lock:
            found = False
            if name in self._services:
                del self._services[name]
                found = True
            if name in self._factories:
                del self._factories[name]
                found = True
            self._health.pop(name, None)
            self._registration_order = [
                n for n in self._registration_order if n != name
            ]
        if found:
            logger.debug("Removed service: %s", name)
        return found

    def list_services(self) -> dict[str, str]:
        """Return all registered services and their health status.

        Returns:
            Mapping of service name to health status string.
        """
        with self._lock:
            return {
                name: self._health.get(name, "unknown")
                for name in self._registration_order
            }

    def set_health(self, name: str, status: str) -> None:
        """Set the health status for a registered service.

        Args:
            name: Service name.
            status: Health status string (e.g. "healthy", "degraded",
                "unhealthy").
        """
        with self._lock:
            if name in self._services or name in self._factories:
                self._health[name] = status
                logger.debug("Health for %s set to %s", name, status)
            else:
                logger.warning(
                    "Cannot set health for unknown service: %s", name
                )

    def get_healthy(self) -> list[str]:
        """Return names of services with healthy status.

        Returns:
            List of service names with health == "healthy".
        """
        with self._lock:
            return [
                name
                for name in self._registration_order
                if self._health.get(name) == "healthy"
            ]

    def clear(self) -> None:
        """Remove all registered services, factories, and health data."""
        with self._lock:
            self._services.clear()
            self._factories.clear()
            self._health.clear()
            self._registration_order.clear()
        logger.debug("Service registry cleared")

    def initialize_all(self) -> dict[str, bool]:
        """Create all lazy services and return per-service success.

        Returns:
            Mapping of service name to whether initialization succeeded.
        """
        results: dict[str, bool] = {}
        with self._lock:
            factory_names = list(self._factories.keys())

        for name in factory_names:
            try:
                self.get(name)
                results[name] = True
                logger.debug("Initialized lazy service: %s", name)
            except Exception:
                results[name] = False
                logger.exception("Failed to initialize service: %s", name)
        return results

    def shutdown_all(self) -> None:
        """Call ``shutdown()`` on services that support it.

        Services are shut down in reverse registration order.
        """
        with self._lock:
            ordered = list(reversed(self._registration_order))
            services_snapshot = dict(self._services)

        for name in ordered:
            service = services_snapshot.get(name)
            if service is None:
                continue
            shutdown_fn = getattr(service, "shutdown", None)
            if callable(shutdown_fn):
                try:
                    shutdown_fn()
                    logger.debug("Shut down service: %s", name)
                except Exception:
                    logger.exception("Error shutting down service: %s", name)
            else:
                logger.debug(
                    "Service %s has no shutdown() method, skipping", name
                )

    def _create_instance(self, factory: Callable[[], Any]) -> Any:
        """Invoke a factory callable with error handling and logging.

        Args:
            factory: Zero-argument callable.

        Returns:
            The created instance.

        Raises:
            Exception: Re-raises any exception from the factory.
        """
        logger.debug("Creating instance from factory: %s", factory)
        instance = factory()
        return instance


def get_registry() -> ServiceRegistry:
    """Return the default module-level ServiceRegistry.

    Creates the singleton on first call.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = ServiceRegistry()
    return _default_registry


def reset_registry() -> ServiceRegistry:
    """Reset the default registry, returning a fresh instance.

    Returns:
        A new empty ServiceRegistry (now the default).
    """
    global _default_registry
    _default_registry = ServiceRegistry()
    return _default_registry
