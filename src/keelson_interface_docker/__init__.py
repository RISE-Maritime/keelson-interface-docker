"""Keelson RPC responder exposing host container control as ``container_control/v1``."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("keelson-interface-docker")
except PackageNotFoundError:
    # Running straight from a source tree with nothing installed. Both real
    # paths -- `uv pip install -e .` and the Dockerfile's `uv pip install
    # --system .` -- write metadata, so this is a developer convenience, not a
    # supported deployment.
    #
    # Read from the metadata rather than repeating the literal here: the
    # release workflow tags the image from the git tag, so a second copy of the
    # version is a second thing that can disagree with it. That is the exact
    # failure keelson's own release workflow was rewritten to prevent.
    __version__ = "0.0.0+unknown"
