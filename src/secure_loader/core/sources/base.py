"""Base types for firmware source providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

ProgressCallback = Callable[[int, int], None]
"""Progress callback receiving ``(bytes_received, bytes_total)``."""


class FirmwareSourceError(RuntimeError):
    """Raised when a firmware source cannot provide the requested blob."""


class FirmwareIdentifier:
    """Keys identifying which firmware image to fetch.

    Section values are derived from the device's 64-bit ``productId`` by
    applying the user-configured :class:`~secure_loader.core.id_sections.IdSectionDef`
    list (see :meth:`~secure_loader.core.firmware.FirmwareHeader.get_sections` and
    :meth:`~secure_loader.core.protocol.DeviceInfo.get_sections`).

    Section values are accessed by name as regular attributes using
    ``__getattr__``, e.g. ``identifier.license_id``.  This keeps callers
    decoupled from the storage representation and allows any configured section
    name to work transparently with :class:`~secure_loader.core.sources.http.HttpFirmwareSource`.

    The ``app_version`` attribute is reserved for the rollback-fetch use case
    (``prevAppVersion`` from the firmware header) and is not a product-ID section.

    Construction::

        sections = device_info.get_sections(config.id_section_defs)
        identifier = FirmwareIdentifier(sections, app_version="0.9.1")
    """

    def __init__(self, sections: dict[str, str], app_version: str | None = None) -> None:
        object.__setattr__(self, "_sections", dict(sections))
        object.__setattr__(self, "app_version", app_version)

    # -------------------------------------------------------------- attribute access

    def __getattr__(self, name: str) -> str:
        """Return the value of section ``name``.

        Only called for names not found in ``__dict__`` (i.e. section names,
        not ``_sections`` or ``app_version``).
        """
        try:
            sections: dict[str, str] = object.__getattribute__(self, "_sections")
            return sections[name]
        except KeyError:
            available = list(object.__getattribute__(self, "_sections"))
            raise AttributeError(
                f"{type(self).__name__} has no section {name!r}. "
                f"Available sections: {available}"
            ) from None

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("FirmwareIdentifier is immutable")

    # -------------------------------------------------------------- helpers

    def get(self, name: str, default: str = "") -> str:
        """Return section value or ``default`` if the section is not present."""
        sections: dict[str, str] = object.__getattribute__(self, "_sections")
        return sections.get(name, default)

    @property
    def section_names(self) -> list[str]:
        """Names of all sections carried by this identifier."""
        return list(object.__getattribute__(self, "_sections"))

    # -------------------------------------------------------------- dunder protocol

    def __repr__(self) -> str:
        sections = object.__getattribute__(self, "_sections")
        app_version = object.__getattribute__(self, "app_version")
        return f"FirmwareIdentifier(sections={sections!r}, app_version={app_version!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FirmwareIdentifier):
            return NotImplemented
        return bool(
            object.__getattribute__(self, "_sections")
            == object.__getattribute__(other, "_sections")
            and object.__getattribute__(self, "app_version")
            == object.__getattribute__(other, "app_version")
        )

    def __hash__(self) -> int:
        sections = object.__getattribute__(self, "_sections")
        app_version = object.__getattribute__(self, "app_version")
        return hash((tuple(sorted(sections.items())), app_version))


class FirmwareSource(ABC):
    """Abstract firmware provider.

    Implementations must be safe to call repeatedly. Long-running operations
    should honour the optional ``progress`` callback so frontends can update
    progress bars.
    """

    @abstractmethod
    def fetch_latest(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        """Return the current/latest firmware blob for ``identifier``."""

    @abstractmethod
    def fetch_previous(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        """Return the previous firmware version indicated by ``identifier.app_version``.

        Typically ``identifier.app_version`` will hold the ``prevAppVersion``
        field of the currently installed image so the provider can locate the
        corresponding older release.
        """
