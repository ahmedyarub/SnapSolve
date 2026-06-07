"""SnapSolve entry point - delegates to app.startup.main()."""
# FORCE PyQt6 initialization at the VERY FIRST entry point
try:
    import PyQt6.QtWebEngineWidgets
except Exception:
    pass

from app.startup import main

if __name__ == "__main__":
    main()
