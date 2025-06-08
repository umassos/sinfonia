from typing import Tuple, List, Optional, Dict, Callable
from multiprocessing import Process


_jobs: List[Tuple[Callable, Dict]] = []


def register(f: Callable, kwargs: Optional[Dict]):
    _jobs.append((f, kwargs))


def start():
    """Start registered daemons (sub-processes)"""
    for j, kwargs in _jobs:
        p = Process(target=j, daemon=True, kwargs=kwargs)
        p.start()
        