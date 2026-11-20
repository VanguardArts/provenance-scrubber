"""Provenance Scrubber — batch detection and removal of embedded provenance
signals (C2PA manifests, EXIF, XMP, IPTC) from images, plus a configurable
pixel-domain transform ladder for degrading latent (invisible) watermarks.

Intended for processing your own content and for authorized security research.
"""

__version__ = "0.2.0"
