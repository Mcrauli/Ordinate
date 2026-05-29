"""ElementDetector — rajapinta kaikille segmentointimoduuleille."""
from __future__ import annotations

from abc import ABC, abstractmethod

import open3d as o3d

from scan2bim.schemas.model import Element


class ElementDetector(ABC):
    @abstractmethod
    def detect(self, cloud: o3d.geometry.PointCloud) -> list[Element]:
        """Tunnistaa elementit pistepilvestä. Schema sisään → schema ulos."""
        ...
