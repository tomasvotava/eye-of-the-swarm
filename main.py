# pygbag only pre-installs a dependency it sees a literal `import` of here; without it, eye's own
# (indirect, several-hops-deep) import of pygame runs against pygbag's broken stub, not the wheel.
import pygame  # noqa: F401

from eye.main import main as main

if __name__ == "__main__":
    main()
