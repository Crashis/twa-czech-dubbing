"""PyInstaller entrypoint; source GUI: python -B -m tools.installer.gui."""
import sys

if len(sys.argv) == 4 and sys.argv[1] == '--self-test':
    from tools.installer.smoke import run
    raise SystemExit(run(sys.argv[2], sys.argv[3]))
else:
    from tools.installer.gui import main
    raise SystemExit(main())
