"""Own disposable namespaces outside the measurement driver's process group."""

import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time


_queue_spec = importlib.util.spec_from_file_location("lab_queue", Path(__file__).with_name("lab_queue.py"))
lab_queue = importlib.util.module_from_spec(_queue_spec)
_queue_spec.loader.exec_module(lab_queue)


LIMIT = 4096
PR_SET_CHILD_SUBREAPER = 36
WORKER = r'''
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-I", "-c", """
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print("READY", flush=True)
time.sleep(120)
"""], stdout=subprocess.PIPE)
if child.stdout.readline() != b"READY\n":
    raise SystemExit(1)
child.stdout.close()
print("READY " + str(child.pid), flush=True)
if sys.argv[1] == "check-crash":
    time.sleep(120)
# Intentionally leave the descendant alive: the independent guard must reap it.
'''


class GuardError(Exception):
    pass


class Interrupted(GuardError):
    def __init__(self, code):
        super().__init__(f"Supervision interrompue (code {code}).")
        self.code = code


def enable_subreaper():
    # Linux PR_SET_CHILD_SUBREAPER: orphaned grandchildren become waitable here.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


class Namespaces:
    """Only named resources created here; never enumerate/delete foreign names."""

    def __init__(self, ip, directory=Path("/run/netns")):
        self.ip, self.directory = ip, directory

    def identity(self, name):
        try:
            info = (self.directory / name).lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(info.st_mode):
            raise GuardError(f"Lien symbolique inattendu pour {name}.")
        return info.st_dev, info.st_ino

    def command(self, action, name, timeout):
        subprocess.run([self.ip, "netns", action, name], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, check=True, timeout=timeout)

    def worker_args(self, gateway, mode):
        return [self.ip, "netns", "exec", gateway,
                sys.executable, "-I", "-c", WORKER, mode]

    def execute(self, args, owner):
        return lab_queue.run_command(args, owner)


class Guard:
    def __init__(self, namespaces, *, timeout=180, cleanup_timeout=10, tempdir=None):
        if not 0 < timeout <= 180 or not 0 < cleanup_timeout <= 10:
            raise ValueError("Délais de supervision invalides.")
        self.namespaces = namespaces
        self.deadline = time.monotonic() + timeout
        self.cleanup_timeout = cleanup_timeout
        self.tempdir = tempdir
        self.interruption = 0
        self.workspace = None
        self.owned = []
        self.uncertain = []
        self.child = None
        self.output = bytearray()
        self.descendant = None
        self.driver_code = None
        self.reaped_descendants = 0
        self.closed = False
        self.queue_report = None
        self.command_child = None

    def check(self):
        if self.interruption:
            raise Interrupted(self.interruption)
        if time.monotonic() >= self.deadline:
            raise GuardError("Échéance indépendante de supervision dépassée.")

    def journal(self, state):
        if self.workspace:
            value = {"schema_version": 1, "kind": "lab_guard_journal", "state": state,
                     "namespaces": [{"name": name, "identity": identity}
                                    for name, identity in self.owned],
                     "uncertain_names": self.uncertain,
                     "driver_pid": self.child.pid if self.child else None}
            if self.queue_report is not None:
                value["queue"] = self.queue_report
            (self.workspace / "owner.json").write_text(json.dumps(value) + "\n")

    def create(self):
        if self.workspace is not None:
            raise GuardError("Ressources déjà réservées par ce superviseur.")
        self.check()
        self.workspace = Path(tempfile.mkdtemp(prefix="coopace-guard.", dir=self.tempdir))
        token = self.workspace.name.removeprefix("coopace-guard.")
        if not re.fullmatch(r"[a-z0-9_]{8}", token):
            raise GuardError("Réservation temporaire invalide.")
        self.journal("creating")
        print(f"Réservation du superviseur : {self.workspace}", file=sys.stderr, flush=True)
        for role in ("c", "g", "s"):
            self.check()
            name = f"cg-{token}-{role}"
            if self.namespaces.identity(name) is not None:
                raise GuardError(f"Collision de nom : {name} ; ressource laissée intacte.")
            # Handlers only set a flag. Record success before checking that flag.
            try:
                self.check()
                self.namespaces.command("add", name,
                                        max(0.001, min(2, self.deadline - time.monotonic())))
            except (OSError, subprocess.SubprocessError):
                # A failed/timed out command may have made a resource. Ownership
                # is ambiguous: log the name, never delete an unconfirmed object.
                self.uncertain.append(name)
                raise
            self.owned.append((name, None))
            identity = self.namespaces.identity(name)
            if identity is None:
                raise GuardError(f"Création de {name} non confirmée.")
            self.owned[-1] = (name, identity)
            self.journal("creating")
            self.check()
        self.journal("armed")

    def start(self, args):
        if self.child is not None:
            raise GuardError("Un pilote est déjà enregistré.")
        self.check()
        self.child = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.PIPE, start_new_session=True)
        # Keep the session leader unreaped until its whole group is signalled.
        # Its PID cannot be reused while it is still our live/zombie child.
        os.set_blocking(self.child.stdout.fileno(), False)
        self.journal("running")
        self.check()

    def exited(self):
        return os.waitid(os.P_PID, self.child.pid,
                         os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None

    def drain(self):
        # Limit work as well as retained bytes, including a continuously writing child.
        try:
            data = os.read(self.child.stdout.fileno(), LIMIT + 1)
        except BlockingIOError:
            return
        self.output.extend(data)
        if len(self.output) > LIMIT:
            raise GuardError("Sortie du pilote trop volumineuse.")

    def monitor(self, mode):
        ready_deadline = time.monotonic() + 5
        crash_sent = False
        while True:
            self.check()
            self.drain()
            if self.descendant is None and b"\n" in self.output:
                match = re.fullmatch(rb"READY ([1-9][0-9]*)\n", self.output)
                if not match:
                    raise GuardError("Annonce du pilote invalide.")
                self.descendant = int(match[1])
                print(f"Pilote : PID {self.child.pid} ; descendant : PID {self.descendant}",
                      file=sys.stderr, flush=True)
                if mode == "check-crash":
                    os.kill(self.child.pid, signal.SIGKILL)
                    crash_sent = True
            if self.exited():
                self.drain()
                if self.descendant is None:
                    raise GuardError("Pilote arrêté avant disponibilité.")
                if mode == "check-crash" and not crash_sent:
                    raise GuardError("Mort forcée du pilote non effectuée.")
                return
            if self.descendant is None and time.monotonic() >= ready_deadline:
                raise GuardError("Pilote indisponible avant le contrôle.")
            time.sleep(0.01)

    def stop_group(self, deadline):
        if self.child is None:
            return
        child = self.child
        try:
            # Do not call poll()/wait() before the last group signal: either
            # would release the PID used as our process-group ownership anchor.
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            grace = min(deadline, time.monotonic() + 0.2)
            while time.monotonic() < grace:
                time.sleep(0.01)
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.driver_code = child.wait(timeout=max(0.001, deadline - time.monotonic()))
            # Subreaper adoption lets us reap the orphaned helpers too. Never
            # wait for arbitrary children or signal a group after releasing PID.
            while True:
                try:
                    pid, _status = os.waitpid(-child.pid, os.WNOHANG)
                except ChildProcessError:
                    break
                if pid:
                    self.reaped_descendants += 1
                elif time.monotonic() >= deadline:
                    raise GuardError("Arrêt des descendants non confirmé.")
                else:
                    time.sleep(0.01)
        finally:
            child.stdout.close()

    def stop_command(self, deadline):
        child = self.command_child
        if child is not None:
            try:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=max(0.001, deadline - time.monotonic()))
                self.command_child = None
            finally:
                child.stdout.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        deadline = time.monotonic() + self.cleanup_timeout
        errors = []
        for stop in (self.stop_command, self.stop_group):
            try:
                stop(deadline)
            except (OSError, GuardError, subprocess.SubprocessError) as error:
                # Preserve namespaces if a process may still hold them alive.
                errors.append(f"arrêt des processus : {error}")
        processes_stopped = not errors
        if processes_stopped:
            for name, expected in reversed(self.owned):
                try:
                    if expected is None or self.namespaces.identity(name) != expected:
                        raise GuardError(f"Identité de {name} non confirmée ; aucune suppression.")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise GuardError("Délai de nettoyage dépassé.")
                    self.namespaces.command("del", name, min(2, remaining))
                    if self.namespaces.identity(name) is not None:
                        raise GuardError(f"Disparition de {name} non confirmée.")
                except (OSError, GuardError, subprocess.SubprocessError) as error:
                    errors.append(str(error))
        if self.uncertain:
            errors.append("création ambiguë : " + ", ".join(self.uncertain))
        if not errors and self.workspace:
            try:
                (self.workspace / "owner.json").unlink(missing_ok=True)
                self.workspace.rmdir()  # Never recursively remove an unknown file.
                if self.workspace.exists():
                    raise GuardError("Réservation temporaire encore visible.")
            except (OSError, GuardError) as error:
                errors.append(str(error))
        if errors:
            self.journal("cleanup_failed")
            raise GuardError("Nettoyage incomplet : " + "; ".join(errors))
        print("Processus récupérés et espaces du contrôle supprimés.", file=sys.stderr, flush=True)


def run_check(mode, namespaces, *, timeout=180, tempdir=None, queue_check=None):
    enable_subreaper()
    guard = Guard(namespaces, timeout=timeout, tempdir=tempdir)
    previous = {}
    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        def interrupted(received, _frame):
            if not guard.interruption:
                guard.interruption = 128 + received
        signal.signal(signum, interrupted)
    try:
        try:
            guard.create()
            if queue_check is not None:
                queue_check.prepare(guard)
            worker_mode = "check-crash" if mode.endswith("-crash") else "check"
            guard.start(namespaces.worker_args(guard.owned[1][0], worker_mode))
            guard.monitor(worker_mode)
            if queue_check is not None:
                queue_check.verify("after_driver_exit")
        finally:
            guard.close()
        guard.check()
        expected = -signal.SIGKILL if mode.endswith("-crash") else 0
        if guard.driver_code != expected or guard.reaped_descendants != 1:
            raise GuardError("Arrêt du pilote ou récupération du descendant non conforme.")
        result = {"schema_version": 1, "kind": "lab_guard_check", "mode": mode,
                "driver_exit_code": guard.driver_code,
                "reaped_descendants": guard.reaped_descendants,
                "driver_pid": guard.child.pid, "descendant_pid": guard.descendant,
                "namespaces": [name for name, _identity in guard.owned],
                "workspace": str(guard.workspace), "cleanup_verified": True,
                "queue_applied": queue_check is not None, "traffic_generated": False}
        if queue_check is not None:
            result["kind"] = "lab_queue_statistics_check" if queue_check.collect_statistics else "lab_queue_check"
            result["queue"] = guard.queue_report
        return result
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def preflight():
    if sys.platform != "linux" or not hasattr(os, "WNOWAIT"):
        raise GuardError("Ce contrôle requiert Linux et waitid/WNOWAIT.")
    if os.geteuid() != 0:
        raise GuardError("Contrôle natif réservé aux privilèges de laboratoire ; consulter docs/LAB_GUARD.md.")
    match = re.search(r"^CapEff:\s*([0-9a-fA-F]+)$", Path("/proc/self/status").read_text(), re.M)
    required = (1 << 12) | (1 << 21)
    if not match or int(match[1], 16) & required != required:
        raise GuardError("CAP_NET_ADMIN et CAP_SYS_ADMIN requises ; aucun espace créé.")
    ip = shutil.which("ip")
    if not ip:
        raise GuardError("Outil ip absent ; aucun espace créé.")
    return Namespaces(ip)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?",
                        choices=("plan", "check", "check-crash", "plan-queue", "check-queue", "check-queue-crash",
                                 "check-queue-stats", "check-queue-stats-crash"),
                        default="plan")
    args = parser.parse_args(argv)
    if args.mode == "plan":
        print("Contrôle prévu : trois espaces Linux neufs, un pilote et un descendant temporaire.\n"
              "check : fin normale du pilote ; check-crash : SIGKILL du pilote après disponibilité.\n"
              "Superviseur indépendant, échéance 180s, nettoyage 10s, suppression des seuls objets possédés.\n"
              "Aucune file, route, adresse, interface physique ou sonde n'est configurée.\n"
              "Le mode plan ne crée aucune ressource et n'exige aucun privilège.")
        return 0
    if args.mode == "plan-queue":
        print(lab_queue.plan())
        return 0
    try:
        namespaces = preflight()
        queue_check = None
        if args.mode.startswith("check-queue"):
            tc = shutil.which("tc")
            if not tc:
                raise GuardError("Outil tc absent ; aucun espace créé.")
            queue_check = lab_queue.QueueCheck(namespaces, tc, collect_statistics="stats" in args.mode)
        result = run_check(args.mode, namespaces, queue_check=queue_check)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Interrupted as error:
        print(str(error), file=sys.stderr)
        return error.code
    except (OSError, GuardError, lab_queue.QueueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
