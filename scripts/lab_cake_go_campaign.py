"""Internal Go/path campaign: collection and final report after cleanup."""

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
verdict = sibling("campaign_verdict", "lab_cake_go_campaign_report.py")
active = path.active


def source_fingerprints():
    return {**path.source_fingerprints(), **{
        str(Path(__file__).with_name(name)): hashlib.sha256(active.go.read(Path(__file__).with_name(name), 1024 * 1024)).hexdigest()
        for name in ("lab_cake_go_campaign.py", "lab_cake_go_campaign_collect.py", "lab_cake_go_campaign_protocol.py",
                     "lab_cake_go_campaign_assess.py", "lab_cake_go_campaign_report.py", "lab-cake-go-campaign.py",
                     "lab_cake_go_campaign_traffic.py", "lab-cake-go-campaign-traffic.py")}}


class Inventory(path.Inventory):
    source_fingerprints = staticmethod(source_fingerprints)


class Journal(active.Journal):
    def __init__(self, target):
        super().__init__(target, limit=16 * 1024 * 1024)


def collect(mode, namespaces, worker, tc, sysctl, ping, binaries, artifacts, *, timeout=180, tempdir=None,
        session_factory=active.go.Session, inventory_factory=None, collector_factory=collection.Collector, journal_factory=Journal,
        path_factory=path.PathCheck, finalizer=None):
    active.require(mode in ("run", "check-crash"), "Mode de campagne inconnu.")
    if inventory_factory is None:
        def inventory_factory(*args):
            return Inventory(*args, ping=ping)
    return active.run(mode, namespaces, worker, tc, sysctl, binaries, artifacts, timeout=timeout, tempdir=tempdir,
                      session_factory=session_factory, inventory_factory=inventory_factory,
                      collector_factory=collector_factory, path_factory=path_factory, journal_factory=journal_factory,
                      report_kind="lab_cake_go_campaign_collection", finalizer=finalizer)


def run(*args, **kwargs):
    """Publish decisions only after operational cleanup and closed evidence."""
    active.require("finalizer" not in kwargs, "Finaliseur de campagne réservé.")
    return collect(*args, **kwargs, finalizer=verdict.finalize)


def plan():
    return ("Campagne CAKE après Go — trois paires repos/charge sur trois espaces neufs.\n"
            "Une installation CAKE 4mbit par Go sur wan DOWN ; activation et passage IPv4 contrôlés.\n"
            "Ordre : idle/loaded, loaded/idle, idle/loaded ; outils neufs et vidage entre phases.\n"
            "60 tentatives TCP, trois transferts de 8 Mio, soit 24 Mio utiles en mode run.\n"
            "check-crash : après la première phase idle, tuer le pilote au ready chargé avant continue ;\n"
            "récupérer ses trois outils et nettoyer, sans qualification des mesures.\n"
            "Propriétaire 180s, pilote 150s, nettoyage 10s ; aucune interface physique ni accès Internet.\n"
            "--worker, --binaries et --artifacts DOSSIER_NEUF_VIDE requis pour exécuter.\n"
            "Rapport global après preuves et nettoyage ; charge et connexions évaluées séparément.\n"
            "Préparation, lanceur et relecture disponibles ; validation native de campagne et bénéfice du foyer à confirmer.\n"
            "Le mode plan ne crée aucune ressource et ne requiert aucun privilège.")
