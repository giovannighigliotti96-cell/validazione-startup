"""Hourly on Giovanni's PC (Task Scheduler): harvest queued Ad Library terms from a home IP, then classify/snowball.
Run: python -X utf8 -m scripts.adlib_local [max_terms]"""
import logging
import sys

from app.services import adlib

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
print(adlib.run_cycle(max_terms=int(sys.argv[1]) if len(sys.argv) > 1 else 4, harvest=True))
