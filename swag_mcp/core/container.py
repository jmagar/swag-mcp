"""Dependency injection container for SWAG MCP."""

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Generic, TypeVar, cast

logger = logging.getLogger(__name__)
T = TypeVar('T')


class ServiceLifetime:
    """Service lifetime management options."""

    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"


class ServiceContainer:
    """Dependency injection container with lifecycle management.

    Provides centralized service registration and resolution with support
    for different service lifetimes (singleton, transient, scoped).
    """

    def __init__(self) -> None:
        """Initialize the service container with empty registries."""
        self._services: dict[type, Any] = {}
        self._factories: dict[type, Callable[[], Any]] = {}
        self._lifetimes: dict[type, str] = {}
        self._scoped_services: dict[str, dict[type, Any]] = defaultdict(dict)
        self._lock = threading.RLock()  # Use RLock for nested calls
        logger.info("Initialized service container")

    def register_singleton(self, service_type: type[T], factory: Callable[[], T]) -> None:
        """Register a singleton service.

        Args:
            service_type: Type of service to register
            factory: Factory function that creates the service instance

        """
        with self._lock:
            self._factories[service_type] = factory
            self._lifetimes[service_type] = ServiceLifetime.SINGLETON
            logger.debug(f"Registered singleton service: {service_type.__name__}")

    def register_transient(self, service_type: type[T], factory: Callable[[], T]) -> None:
        """Register a transient service (new instance each time).

        Args:
            service_type: Type of service to register
            factory: Factory function that creates the service instance

        """
        with self._lock:
            self._factories[service_type] = factory
            self._lifetimes[service_type] = ServiceLifetime.TRANSIENT
            logger.debug(f"Registered transient service: {service_type.__name__}")

    def register_scoped(self, service_type: type[T], factory: Callable[[], T]) -> None:
        """Register a scoped service (one instance per scope).

        Args:
            service_type: Type of service to register
            factory: Factory function that creates the service instance

        """
        with self._lock:
            self._factories[service_type] = factory
            self._lifetimes[service_type] = ServiceLifetime.SCOPED
            logger.debug(f"Registered scoped service: {service_type.__name__}")

    def register_instance(self, service_type: type[T], instance: T) -> None:
        """Register a service instance directly.

        Args:
            service_type: Type of service
            instance: Pre-created instance to register

        """
        with self._lock:
            self._services[service_type] = instance
            self._lifetimes[service_type] = ServiceLifetime.SINGLETON
            logger.debug(f"Registered service instance: {service_type.__name__}")

    def get_service(self, service_type: type[T], scope: str = "default") -> T:
        """Get a service instance.

        Args:
            service_type: Type of service to get
            scope: Scope identifier for scoped services

        Returns:
            Service instance

        Raises:
            ValueError: If service is not registered

        """
        with self._lock:
            # Check if instance already exists (singleton)
            if service_type in self._services:
                return cast('T', self._services[service_type])

            # Check if factory exists
            if service_type not in self._factories:
                raise ValueError(f"No service registered for type: {service_type.__name__}")

            lifetime = self._lifetimes[service_type]
            factory = self._factories[service_type]

            if lifetime == ServiceLifetime.SINGLETON:
                # Create and cache singleton
                if service_type not in self._services:
                    logger.debug(f"Creating singleton service: {service_type.__name__}")
                    self._services[service_type] = factory()
                return cast('T', self._services[service_type])

            elif lifetime == ServiceLifetime.TRANSIENT:
                # Always create new instance
                logger.debug(f"Creating transient service: {service_type.__name__}")
                return cast('T', factory())

            elif lifetime == ServiceLifetime.SCOPED:
                # Create per scope
                if service_type not in self._scoped_services[scope]:
                    logger.debug(
                        f"Creating scoped service: {service_type.__name__} (scope: {scope})"
                    )
                    self._scoped_services[scope][service_type] = factory()
                return cast('T', self._scoped_services[scope][service_type])

            else:
                raise ValueError(f"Unknown service lifetime: {lifetime}")

    def clear_scope(self, scope: str) -> None:
        """Clear all services for a specific scope.

        Args:
            scope: Scope identifier to clear

        """
        with self._lock:
            if scope in self._scoped_services:
                count = len(self._scoped_services[scope])
                del self._scoped_services[scope]
                logger.debug(f"Cleared scope '{scope}' with {count} services")

    def is_registered(self, service_type: type) -> bool:
        """Check if a service type is registered.

        Args:
            service_type: Type to check

        Returns:
            True if registered, False otherwise

        """
        with self._lock:
            return (service_type in self._services or
                   service_type in self._factories)

    def get_registered_services(self) -> dict[str, str]:
        """Get information about registered services.

        Returns:
            Dictionary of service name -> lifetime

        """
        with self._lock:
            result = {}

            # Add services with instances
            for service_type in self._services:
                result[service_type.__name__] = "instance"

            # Add services with factories
            for service_type, lifetime in self._lifetimes.items():
                if service_type not in self._services:
                    result[service_type.__name__] = lifetime

            return result

    def reset(self) -> None:
        """Reset the container, clearing all services and registrations."""
        with self._lock:
            self._services.clear()
            self._factories.clear()
            self._lifetimes.clear()
            self._scoped_services.clear()
            logger.info("Reset service container")


class ServiceRegistration(Generic[T]):
    """Fluent interface for service registration."""

    def __init__(self, container: ServiceContainer, service_type: type[T]):
        """Initialize service registration with container and service type."""
        self._container = container
        self._service_type = service_type

    def as_singleton(self, factory: Callable[[], T]) -> 'ServiceRegistration[T]':
        """Register as singleton service."""
        self._container.register_singleton(self._service_type, factory)
        return self

    def as_transient(self, factory: Callable[[], T]) -> 'ServiceRegistration[T]':
        """Register as transient service."""
        self._container.register_transient(self._service_type, factory)
        return self

    def as_scoped(self, factory: Callable[[], T]) -> 'ServiceRegistration[T]':
        """Register as scoped service."""
        self._container.register_scoped(self._service_type, factory)
        return self

    def as_instance(self, instance: T) -> 'ServiceRegistration[T]':
        """Register as instance."""
        self._container.register_instance(self._service_type, instance)
        return self


class ContainerBuilder:
    """Builder for configuring service container."""

    def __init__(self) -> None:
        """Initialize container builder with a new service container."""
        self._container = ServiceContainer()

    def register(self, service_type: type[T]) -> ServiceRegistration[T]:
        """Register a service type.

        Args:
            service_type: Type to register

        Returns:
            ServiceRegistration for fluent configuration

        """
        return ServiceRegistration(self._container, service_type)

    def build(self) -> ServiceContainer:
        """Build and return the configured container.

        Returns:
            Configured ServiceContainer instance

        """
        return self._container


# Global container instance
container = ServiceContainer()


# Decorator for automatic service registration
def service(lifetime: str = ServiceLifetime.SINGLETON) -> Callable[[type[T]], type[T]]:
    """Automatically register a service.

    Args:
        lifetime: Service lifetime (singleton, transient, or scoped)

    Example:
        >>> @service(lifetime=ServiceLifetime.SINGLETON)
        ... class MyService:
        ...     pass

    """
    def decorator(cls: type[T]) -> type[T]:
        def factory() -> T:
            return cls()
        if lifetime == ServiceLifetime.SINGLETON:
            container.register_singleton(cls, factory)
        elif lifetime == ServiceLifetime.TRANSIENT:
            container.register_transient(cls, factory)
        elif lifetime == ServiceLifetime.SCOPED:
            container.register_scoped(cls, factory)
        else:
            raise ValueError(f"Unknown service lifetime: {lifetime}")

        return cls
    return decorator
