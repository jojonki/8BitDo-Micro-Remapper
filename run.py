"""Entry point (also used for PyInstaller builds)."""
import multiprocessing

from remapper.gui import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
