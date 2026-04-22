"""Single source of truth for version + app name.

Read by the About dialog (``gui/about.py``), ``pyproject.toml`` (kept in sync
manually), and the Inno Setup installer build script at
``packaging/build_installer.ps1``.
"""

__app_name__ = "ACB Tool"
__version__  = "0.1.0"
__author__   = "Mogolt"
__repo_url__ = ""  # placeholder — fill in when the repo is public
