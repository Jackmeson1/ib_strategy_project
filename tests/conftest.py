import os
import sys

# Ensure project root is on sys.path for tests
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Provide required environment variable for configuration loading during tests
os.environ.setdefault("IB_ACCOUNT_ID", "TEST")
