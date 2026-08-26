"""Packaged GUI example definitions and workspace copying."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path, PurePosixPath, PureWindowsPath


class ExampleResourceError(RuntimeError):
    """Raised when a packaged example cannot be safely copied."""


def _resource_path(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty resource path")
    text = value.strip()
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or PureWindowsPath(text).is_absolute()
        or "\\" in text
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"{field} must be a normalized relative POSIX path")
    return path.as_posix()


@dataclass(frozen=True, slots=True)
class ExampleDefinition:
    """One menu entry and every resource needed by its input table."""

    label: str
    input_resource: str
    supporting_resources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("ExampleDefinition.label must be non-empty")
        input_resource = _resource_path(
            self.input_resource,
            field="ExampleDefinition.input_resource",
        )
        if PurePosixPath(input_resource).suffix.lower() not in {
            ".csv",
            ".xlsx",
            ".xlsm",
        }:
            raise ValueError("ExampleDefinition.input_resource must be a case table")
        try:
            supporting = tuple(self.supporting_resources)
        except TypeError as exc:
            raise TypeError(
                "ExampleDefinition.supporting_resources must be iterable"
            ) from exc
        supporting = tuple(
            _resource_path(
                value,
                field="ExampleDefinition.supporting_resources item",
            )
            for value in supporting
        )
        all_resources = (input_resource, *supporting)
        if len(all_resources) != len(set(all_resources)):
            raise ValueError("ExampleDefinition resources must be unique")
        object.__setattr__(self, "label", self.label.strip())
        object.__setattr__(self, "input_resource", input_resource)
        object.__setattr__(self, "supporting_resources", supporting)

    @property
    def resources(self) -> tuple[str, ...]:
        return (self.input_resource, *self.supporting_resources)


class ExampleLibrary:
    """Locate source/install resources and copy an example without overwriting."""

    def __init__(self, resource_root: Traversable | None = None) -> None:
        self._resource_root = resource_root

    def _root(self) -> Traversable:
        if self._resource_root is not None:
            return self._resource_root
        packaged = resources.files("panelsolver").joinpath("_examples")
        if packaged.is_dir():
            return packaged
        checkout = Path(__file__).resolve().parents[3] / "examples"
        if checkout.is_dir():
            return checkout
        raise ExampleResourceError(
            "Panel Solver example resources are not available in this installation."
        )

    def copy_example(
        self,
        example: ExampleDefinition,
        destination: str | Path,
    ) -> Path:
        """Copy one complete example tree and return its copied input path."""
        if not isinstance(example, ExampleDefinition):
            raise TypeError("example must be an ExampleDefinition")
        target_root = Path(destination).expanduser().resolve(strict=False)
        if target_root.exists() and not target_root.is_dir():
            raise ExampleResourceError(
                f"Example destination is not a directory: {target_root}"
            )

        payloads: list[tuple[Path, bytes]] = []
        root = self._root()
        for relative in example.resources:
            source = root.joinpath(*PurePosixPath(relative).parts)
            if not source.is_file():
                raise ExampleResourceError(f"Example resource is missing: {relative}")
            payload = source.read_bytes()
            target = target_root.joinpath(*PurePosixPath(relative).parts)
            if target.exists():
                if not target.is_file() or target.read_bytes() != payload:
                    raise ExampleResourceError(
                        f"Example copy would overwrite an existing file: {target}"
                    )
                continue
            payloads.append((target, payload))

        for target, payload in payloads:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        return target_root.joinpath(*PurePosixPath(example.input_resource).parts)


__all__ = (
    "ExampleDefinition",
    "ExampleLibrary",
    "ExampleResourceError",
)
