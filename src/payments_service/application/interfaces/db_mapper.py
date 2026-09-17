from abc import abstractmethod
from typing import Protocol, TypeVar

T = TypeVar("T", contravariant=True)


class DbMapperProtocol(Protocol[T]):
    """Protocol for database mappers used in Unit of Work."""

    @abstractmethod
    def insert(self, model: T) -> None:
        """Insert a new model into the database."""
        ...

    @abstractmethod
    def update(self, model: T) -> None:
        """Update an existing model in the database."""
        ...

    @abstractmethod
    def delete(self, model: T) -> None:
        """Delete a model from the database."""
        ...
