"""python -m apexlinux            the APEX app (settings, widget gallery)
python -m apexlinux --desktop  the desktop widgets (one host per session)"""
import sys
import traceback

PACKAGES = """APEX needs GTK 3, WebKit2GTK 4.1 and PyGObject (gtk-layer-shell too on Wayland):
  Arch:          sudo pacman -S python-gobject gtk3 webkit2gtk-4.1 gtk-layer-shell
  Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-gtklayershell-0.1
  Fedora:        sudo dnf install python3-gobject gtk3 webkit2gtk4.1 gtk-layer-shell"""


def main() -> None:
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")  # else PyGObject may pick Gdk 4 when both are installed
        gi.require_version("WebKit2", "4.1")
    except (ImportError, ValueError) as e:
        sys.exit(f"{e}\n\n{PACKAGES}")

    from .host import log_error

    def crash(kind: type[BaseException], value: BaseException, tb: object) -> None:
        log_error("".join(traceback.format_exception(kind, value, tb)))  # GTK callbacks report here too
        sys.__excepthook__(kind, value, tb)

    sys.excepthook = crash
    if "--desktop" in sys.argv[1:]:
        from .desktop import run
    else:
        from .app import run
    run()


main()
