"""ElementDetector-rajapinta + DetectorRegistry. Sisään: o3d.PointCloud → ulos: StructuralModel."""
from __future__ import annotations

from abc import ABC, abstractmethod

import open3d as o3d

from scan2bim.schemas.model import StructuralModel

_REGISTRY: dict[str, type[ElementDetector]] = {}


class ElementDetector(ABC):
    @abstractmethod
    def detect(self, cloud: o3d.geometry.PointCloud) -> StructuralModel:
        ...


class DetectorRegistry:
    @classmethod
    def register(cls, name: str):
        def decorator(klass: type[ElementDetector]) -> type[ElementDetector]:
            _REGISTRY[name] = klass
            return klass
        return decorator

    @classmethod
    def get(cls, name: str) -> type[ElementDetector]:
        if name not in _REGISTRY:
            raise KeyError(f"Tuntematon detektori: {name!r}. Saatavilla: {list(_REGISTRY)}")
        return _REGISTRY[name]

    @classmethod
    def names(cls) -> list[str]:
        return list(_REGISTRY)
