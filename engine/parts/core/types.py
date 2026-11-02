# parts/core/types.py
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class NodeResult:
    """
    Standard result object returned by every node.
    """
    node: str
    success: bool
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None
