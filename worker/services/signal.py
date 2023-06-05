import datetime
import inspect
import sys
from typing import Protocol, Optional, runtime_checkable
from dataclasses import dataclass
from db import get_conn, dictfetchone
