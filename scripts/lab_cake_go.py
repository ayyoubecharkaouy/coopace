"""Go CAKE DOWN control under the existing independent namespace guard."""

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import stat
import struct
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location("cake_go_protocol", Path(__file__).with_name("lab_cake_go_protocol.py"))
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)
cake, Error, require = protocol.cake, protocol.Error, protocol.require
spec = importlib.util.spec_from_file_location("cake_go_guard", Path(__file__).with_name("lab-guard.py"))
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)

# Fresh, single-threaded Python enters the target before exec starts Go. All
# source FDs are duplicated above the destination range before remapping them.
BOOTSTRAP = r'''
import fcntl, os, sys
sources = [int(v) for v in sys.argv[1].split(",")]
copies = [fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 32) for fd in sources]
for destination, source in zip(range(3, 8), copies[:5]):
    os.dup2(source, destination, inheritable=True)
executable = copies[5]
for fd in set(sources + copies[:5]):
    if fd not in {0, 1, 2, 3, 4, 5, 6, 7, executable}:
        os.close(fd)
os.setns(5, os.CLONE_NEWNET)
os.execve("/proc/self/fd/" + str(executable), sys.argv[2:], {"LANG":"C", "LC_ALL":"C"})
'''


def read(path, limit, identity=None):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and (identity is None or (info.st_dev, info.st_ino) == identity), "Identité de pièce modifiée.")
        data = stream.read(limit + 1)
    require(len(data) <= limit, "Pièce Go trop volumineuse.")
    return data


def tool(path):
    path = Path(path).resolve(strict=True)
    data = read(path, 64 * 1024 * 1024)
    require(path.is_file() and os.access(path, os.X_OK) and data.startswith(b"\x7fELF"), "Exécutable ELF requis.")
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def exclusive(path, flags=0):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | flags, 0o600)
    try:
        if os.geteuid() == 0:
            owner = path.parent.stat()
            os.fchown(descriptor, owner.st_uid, owner.st_gid)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def source_fingerprints():
    return {str(Path(__file__).with_name(name)): hashlib.sha256(read(Path(__file__).with_name(name), 1024*1024)).hexdigest()
            for name in ("lab-cake-go.py", "lab_cake_go.py", "lab_cake_go_protocol.py", "lab-guard.py", "lab_queue.py", "lab_cake.py")}


def save(path, value):
    descriptor = exclusive(path)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())


class DownLink(cake.CakeCheck):
    def prepare(self, owner):
        self.owner = owner
        self.producer = {**cake.producer(self.execute([self.tc, "-V"])), "tc_path": self.tc}
        self.prepare_link(owner)
        self.report = {"namespace": self.gateway, "interface": "wan", "link_state": "DOWN",
                       "kind": "cake", "handle": "10:", "producer": self.producer, "before": self.read()}
        cake.queue.initial_qdisc(json.dumps(self.report["before"]["qdiscs"]).encode())
        owner.queue_report = self.report
        owner.journal("go_link_prepared")
        # The supervisor does not add CAKE: only the Go worker may do that.

    def verify(self, label):
        for namespace, interface in ((self.gateway, "wan"), (self.server, "eth0")):
            expected = dict(self.owner.owned)[namespace]
            require(self.owner.namespaces.identity(namespace) == expected, "Identité du lien relu non possédée.")
            rows = self.links(namespace)
            require(len(rows) == 2 and {r.get("ifname") for r in rows} == {"lo", interface}, "Interfaces DOWN non confirmées.")
            row = next(r for r in rows if r.get("ifname") == interface)
            require(isinstance(row.get("flags"), list) and all(isinstance(f, str) for f in row["flags"]) and "UP" not in row["flags"], "Lien activé après le contrôle Go.")
        super().verify(label)


class GoGuard(guards.Guard):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.post_exit_error = None

    def stop_group(self, deadline):
        try:
            super().stop_group(deadline)
            if self.session is not None:
                try:
                    self.session.drain()
                    if self.session.applied is not None:
                        previous = self.deadline
                        try:
                            self.deadline = min(self.deadline, deadline)
                            self.session.link.verify("after_driver_exit")
                        finally:
                            self.deadline = previous
                except (OSError, ValueError, TypeError, KeyError, Error, guards.GuardError, guards.lab_queue.QueueError, subprocess.SubprocessError) as error:
                    # Processes are stopped. Still remove owned namespaces,
                    # while retaining this verification failure in the result.
                    self.post_exit_error = error
        finally:
            if self.session is not None:
                self.session.close()
            if self.child is not None and self.child.stderr is not None:
                self.child.stderr.close()


class Session:
    def __init__(self, owner, tools, folder, link):
        self.owner, self.tools, self.folder, self.link = owner, tools, folder, link
        self.fds, self.control, self.events = [], None, None
        self.buffer, self.event_bytes, self.stderr_bytes = bytearray(), 0, bytearray()
        self.raw_events = bytearray()
        self.journal_identity = None
        self.applied = None
        self.target, self.original = None, None
        self.summary = None
        self.token = owner.workspace.name.removeprefix("coopace-guard.")

    def keep(self, fd):
        self.fds.append(fd)
        return fd

    def identity(self, fd):
        info = os.fstat(fd)
        require(fcntl.ioctl(fd, 0xb703) == os.CLONE_NEWNET, "Descripteur réseau requis.")
        return {"device": info.st_dev, "inode": info.st_ino}

    def namespace_fds(self):
        name, expected = self.owner.owned[1]
        target = self.keep(os.open(self.owner.namespaces.directory / name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW))
        original = self.keep(os.open("/proc/thread-self/ns/net", os.O_RDONLY | os.O_CLOEXEC))
        self.target, self.original = self.identity(target), self.identity(original)
        require((self.target["device"], self.target["inode"]) == expected
                and self.target != self.original, "Espace cible non possédé ou identique à l’origine.")
        return target, original

    def launch_args(self, sources):
        worker = self.tools["worker"]
        flags = ["--session-id", self.token, "--ip", self.tools["ip"]["path"], "--ip-sha256", self.tools["ip"]["sha256"],
                 "--tc", self.tools["tc"]["path"], "--tc-sha256", self.tools["tc"]["sha256"]]
        return [self.tools["python"]["path"], "-I", "-S", "-c", BOOTSTRAP, ",".join(map(str, sources)), worker["path"], *flags]

    def start(self):
        owner = self.owner
        target, original = self.namespace_fds()
        control_read, self.control = os.pipe2(os.O_CLOEXEC)
        for fd in (control_read, self.control): self.keep(fd)
        self.events, event_write = os.pipe2(os.O_CLOEXEC)
        for fd in (self.events, event_write): self.keep(fd)
        journal = self.keep(exclusive(self.folder / "worker.jsonl", os.O_APPEND))
        info = os.fstat(journal)
        self.journal_identity = (info.st_dev, info.st_ino)
        os.fsync(journal)
        directory = os.open(self.folder, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
        worker_fd = self.keep(os.open(self.tools["worker"]["path"], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC))
        with os.fdopen(os.dup(worker_fd), "rb") as stream:
            require(hashlib.sha256(stream.read(64 * 1024 * 1024 + 1)).hexdigest() == self.tools["worker"]["sha256"], "Binaire Go modifié avant exec.")
        sources = [control_read, event_write, target, original, journal, worker_fd]
        owner.check()
        require(owner.child is None, "Un processus est déjà possédé.")
        owner.child = subprocess.Popen(self.launch_args(sources), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, pass_fds=tuple(sources), start_new_session=True,
                                       env={"LANG": "C", "LC_ALL": "C"})
        for fd in (control_read, event_write, journal, worker_fd):
            os.close(fd); self.fds.remove(fd)
        for fd in (self.control, self.events, owner.child.stdout.fileno(), owner.child.stderr.fileno()): os.set_blocking(fd, False)
        owner.journal("go_running")
        owner.check()

    def drain(self):
        child = self.owner.child
        if child is None: return
        # Base Guard closes stdout after reaping; stderr remains open here.
        if not child.stdout.closed:
            try: data = os.read(child.stdout.fileno(), 4097)
            except BlockingIOError: data = b""
            require(not data, "Sortie stdout inattendue du processus interne.")
        for _ in range(9):
            try: data = os.read(child.stderr.fileno(), 8192)
            except BlockingIOError: break
            if not data: break
            remaining = 65536 - len(self.stderr_bytes)
            self.stderr_bytes.extend(data[:remaining])
            require(len(data) <= remaining, "Diagnostic Go trop volumineux.")

    def send(self, value, limit):
        data = protocol.encode(value, limit)
        deadline = min(self.owner.deadline, time.monotonic() + 5)
        while data:
            self.owner.check(); self.drain()
            require(time.monotonic() < deadline, "Canal Go bloqué en écriture.")
            try: count = os.write(self.control, data)
            except BlockingIOError: count = 0
            if count: data = data[count:]
            else: time.sleep(0.005)

    def receive(self, expected):
        deadline = min(self.owner.deadline, time.monotonic() + 5)
        while True:
            self.owner.check(); self.drain()
            require(time.monotonic() < deadline, "Événement Go indisponible avant l’échéance.")
            if len(self.buffer) >= 4:
                size = struct.unpack("!I", self.buffer[:4])[0]
                require(0 < size <= protocol.EVENT_LIMIT, "Longueur d’événement Go invalide.")
                if len(self.buffer) >= size + 4:
                    raw = bytes(self.buffer[4:size + 4]); del self.buffer[:size + 4]
                    return protocol.event(raw, self.token, expected)
            try: data = os.read(self.events, 8192)
            except BlockingIOError: data = None
            if data is not None:
                require(data, "Canal Go fermé avant l’événement attendu.")
                self.capture(data)
                self.buffer.extend(data)
            else: time.sleep(0.005)

    def capture(self, data):
        remaining = protocol.OUTPUT_LIMIT - len(self.raw_events)
        self.raw_events.extend(data[:remaining])
        self.event_bytes += len(data)
        require(self.event_bytes <= protocol.OUTPUT_LIMIT, "Budget de sortie Go dépassé.")

    def no_extra_event(self):
        try: extra = os.read(self.events, 8192)
        except BlockingIOError: extra = b""
        if extra: self.capture(extra)
        require(not self.buffer and not extra, "Événement Go supplémentaire ou prématuré.")

    def validate(self, stage):
        self.summary = protocol.journal(read(self.folder / "worker.jsonl", protocol.JOURNAL_LIMIT, self.journal_identity), self.token,
                                        self.tools, self.target, self.original, self.owner.child.pid, stage, self.applied)
        return self.summary

    def monitor(self, mode):
        self.send({"schema_version": 1, "kind": "lab_cake_worker_request", "session_id": self.token,
                   "purpose": "cake_down_control", "reference": protocol.REFERENCE, "namespace_identity": self.target}, 4096)
        self.receive("ready"); self.validate("ready"); self.no_extra_event()
        require(not self.owner.exited(), "Processus Go arrêté avant apply.")
        self.send({"schema_version": 1, "kind": "lab_cake_worker_control", "session_id": self.token, "action": "apply"}, 1024)
        self.applied = self.receive("applied"); self.validate("applied"); self.no_extra_event()
        self.link.verify("after_add")
        if mode == "check-crash":
            os.kill(self.owner.child.pid, signal.SIGKILL)
        else:
            self.send({"schema_version": 1, "kind": "lab_cake_worker_control", "session_id": self.token, "action": "finish"}, 1024)
        deadline = min(self.owner.deadline, time.monotonic() + 5)
        while not self.owner.exited():
            self.owner.check(); self.drain()
            require(time.monotonic() < deadline, "Processus Go non arrêté après le contrôle.")
            time.sleep(0.005)
        self.drain(); self.no_extra_event()

    def close(self):
        failures = []
        for fd in self.fds:
            try: os.close(fd)
            except OSError as error: failures.append(error)
        self.fds.clear()
        if failures: raise Error("Fermeture des références non confirmée.") from failures[0]


def run(mode, namespaces, worker, tc, artifacts, *, session_factory=Session, timeout=180, tempdir=None):
    require(mode in ("check", "check-crash"), "Mode Go inconnu.")
    require(artifacts.is_dir() and not any(artifacts.iterdir()), "Dossier de preuves neuf et vide requis.")
    tools = {"worker": tool(worker), "ip": tool(namespaces.ip), "tc": tool(tc), "python": tool(sys.executable)}
    namespaces.ip = tools["ip"]["path"]
    sources = source_fingerprints()
    save(artifacts / "environment.json", {"tools": tools, "source_sha256": sources, "kernel": platform.release(),
                                        "python": sys.version, "invocation": {"mode": mode, "purpose": "cake_down_control", "reference": protocol.REFERENCE}, "bootstrap_sha256": hashlib.sha256(BOOTSTRAP.encode()).hexdigest()})
    guards.enable_subreaper()
    owner = GoGuard(namespaces, timeout=timeout, tempdir=tempdir)
    previous = {}
    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        def interrupted(received, _frame): owner.interruption = owner.interruption or 128 + received
        signal.signal(signum, interrupted)
    result = {"schema_version": 1, "kind": "lab_cake_go_control", "mode": mode, "reference": protocol.REFERENCE,
              "traffic_generated": False, "active_path_verified": False, "link_state": "DOWN", "cleanup_verified": False,
              "state": "failed", "tools": tools}
    failure = None
    try:
        try:
            owner.create()
            link = DownLink(namespaces, tools["tc"]["path"]); link.prepare(owner)
            for name, expected in owner.owned:
                require(namespaces.identity(name) == expected, "Identité d’espace modifiée avant lancement.")
            for name, spec in tools.items(): require(tool(spec["path"]) == spec, "Exécutable modifié avant lancement.")
            require(source_fingerprints() == sources, "Sources modifiées avant lancement.")
            owner.session = session_factory(owner, tools, artifacts, link)
            owner.session.start(); owner.session.monitor(mode)
        finally:
            owner.close()
            result["cleanup_verified"] = True
        owner.check()
        require(owner.post_exit_error is None, f"Relecture après arrêt non confirmée : {owner.post_exit_error}")
        require(owner.driver_code == (-9 if mode == "check-crash" else 0), "Code réel Go incompatible.")
        result["journal"] = owner.session.validate("applied" if mode == "check-crash" else "finished")
        for name, spec in tools.items(): require(tool(spec["path"]) == spec, "Exécutable modifié pendant le contrôle.")
        require(source_fingerprints() == sources, "Sources modifiées pendant le contrôle.")
        result["state"] = "complete"
    except BaseException as error:
        failure = error
        result["error"] = str(error)
    finally:
        try:
            if owner.session is not None:
                owner.session.close()
                for filename, data in (("worker.stderr", owner.session.stderr_bytes), ("events.bin", owner.session.raw_events)):
                    descriptor = exclusive(artifacts / filename)
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(data); stream.flush(); os.fsync(stream.fileno())
            result.update(worker_pid=owner.child.pid if owner.child else None, worker_exit_code=owner.driver_code,
                          reaped_descendants=owner.reaped_descendants, namespaces=[name for name, _ in owner.owned],
                          workspace=str(owner.workspace), queue=owner.queue_report)
            save(artifacts / "report.json", result)
        finally:
            for signum, handler in previous.items(): signal.signal(signum, handler)
    if failure is not None: raise failure
    return result


def plan():
    return ("Contrôle CAKE Go DOWN : trois espaces neufs et veth wan/eth0 sans activation.\n"
            "Le superviseur crée le lien ; seul Go ajoute le profil fixe après apply.\n"
            "Entrée réseau avant Go ; canaux 3/4, cible 5, origine 6, journal privé 7.\n"
            "check : fin normale ; check-crash : SIGKILL après applied durable.\n"
            "Relecture indépendante, récupération du groupe puis retrait des seuls objets possédés.\n"
            "Preuves conservées dans un dossier neuf ; aucune référence WAN ni mesure de gain.\n"
            "Le mode plan ne crée aucune ressource et ne requiert aucun privilège.")
