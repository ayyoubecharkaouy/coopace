"""Internal Go/path/campaign collection; scientific assessment is not delivered."""

import hashlib
import importlib.util
from pathlib import Path


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


path = sibling("campaign_path", "lab_cake_go_path_control.py")
collection = sibling("campaign_collection", "lab_cake_go_campaign_collect.py")
active = path.active


def source_fingerprints():
    return {**path.source_fingerprints(), **{
        str(Path(__file__).with_name(name)): hashlib.sha256(active.go.read(Path(__file__).with_name(name), 1024 * 1024)).hexdigest()
        for name in ("lab_cake_go_campaign.py", "lab_cake_go_campaign_collect.py", "lab_cake_go_campaign_protocol.py",
                     "lab_cake_go_campaign_traffic.py", "lab-cake-go-campaign-traffic.py")}}


class Inventory(path.Inventory):
    source_fingerprints = staticmethod(source_fingerprints)


class Journal(active.Journal):
    def __init__(self, target):
        super().__init__(target, limit=16 * 1024 * 1024)


def run(mode, namespaces, worker, tc, sysctl, ping, binaries, artifacts, *, timeout=180, tempdir=None,
        session_factory=active.go.Session, inventory_factory=None, collector_factory=collection.Collector, journal_factory=Journal,
        path_factory=path.PathCheck):
    active.require(mode in ("run", "check-crash"), "Mode de campagne inconnu.")
    if inventory_factory is None:
        def inventory_factory(*args):
            return Inventory(*args, ping=ping)
    return active.run(mode, namespaces, worker, tc, sysctl, binaries, artifacts, timeout=timeout, tempdir=tempdir,
                      session_factory=session_factory, inventory_factory=inventory_factory,
                      collector_factory=collector_factory, path_factory=path_factory, journal_factory=journal_factory,
                      report_kind="lab_cake_go_campaign_collection")
