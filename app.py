import sys
import security
security.ensure_integrity_module()
import integrity
from security import enforce_runtime_authorization
from desktop_app import main


if __name__ == "__main__":
    security.ensure_integrity_module()
    enforce_runtime_authorization()
    main()
