"""pytest bootstrap — put mask_prod_data.py (one dir up) on sys.path.

conftest.py is imported by pytest before test collection, so test
modules can `import mask_prod_data` at the top like a normal import.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
