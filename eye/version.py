"""The running build's version, as stamped by the Makefile's build targets."""


def game_version() -> str | None:
    """Return the release version the build was stamped with (e.g. ``"1.1.1"``), or ``None``
    when running from an unstamped source tree.
    """
    # Neither the web nor the native build installs `eye`, so `importlib.metadata` can't see it.
    try:
        from eye._version import VERSION
    except ImportError:
        return None
    return str(VERSION)
