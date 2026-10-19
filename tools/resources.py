"""Locate public payload data without consulting cwd or private configuration."""
from pathlib import Path
import sys

VERSION = '1.3.0'
ROOT = (Path(sys.executable).resolve().parent / 'payload' if getattr(sys, 'frozen', False)
        else Path(__file__).resolve().parents[1])
