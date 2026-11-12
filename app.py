import sys
from security import require_launch_authorization
from desktop_app import main


if __name__ == "__main__":
    if not require_launch_authorization():
        sys.exit(0)
    main()