"""Cross-run alignment.

Alignment is by feature name, not by raw node correspondence: once each run has
been projected into a declared feature schema, runs line up by construction
(DESIGN-FEATURE-PROJECTION.md §11).
"""

from agentseism.alignment.features import FeatureColumn, align_features

__all__ = ["FeatureColumn", "align_features"]
