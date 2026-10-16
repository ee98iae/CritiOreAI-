import os

from app.data import DEMO_PATH

# The API tests assert on the synthetic demo set, which has known Ni/Co/Cu sites.
# test_real_data.py checks the real default file separately.
os.environ["CRITIORE_OCCURRENCES"] = str(DEMO_PATH)
