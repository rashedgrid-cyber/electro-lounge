import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

REGISTRY_FILE = Path("config/source-registry.json")
OUTPUT_FILE = Path("data/opportunities.json")
