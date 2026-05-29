"""ElementDetector — rajapinta kaikille segmentointimoduuleille."""
from __future__ import annotations

from abc import ABC, abstractmethod

import open3d as o3d

from scan2bim.schemas.model import Element


class ElementDetector(ABC):
    @abstractmethod
    def detect(
        self,
        cloud: o3d.geometry.PointCloud,
    ) -> tuple[list[Element], o3d.geometry.PointCloud]:
        """Tunnistaa elementit pistepilvestä.

        Palauttaa:
            (elementit, jäljellä_oleva_pilvi)
            — jäljellä_oleva_pilvi = alkuperäinen pilvi ilman tämän
              detektorin inlier-pisteitä.
        """
        ...
