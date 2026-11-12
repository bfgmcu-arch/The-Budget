import integrity
import sys
from security import enforce_runtime_authorization
from desktop_app import main


if __name__ == "__main__":
    enforce_runtime_authorization()
    main()
