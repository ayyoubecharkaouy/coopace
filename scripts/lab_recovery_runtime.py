"""Bounded, recorded processes and pinned executables for the recovery lab."""

import hashlib
import fcntl
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import time


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guards = sibling("recovery_guard", "lab-guard.py")
cake = sibling("recovery_cake", "lab_cake.py")
Error = cake.Error


def require(condition, message):
    if not condition:
        raise Error(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def network_namespace_identity(fd):
    # Linux amd64 NS_GET_NSTYPE = _IO(0xb7, 3), matching namespace_linux.go.
    require(fcntl.ioctl(fd, 0xb703) == 0x40000000, "Descripteur de namespace réseau requis.")
    info = os.fstat(fd)
    return info.st_dev, info.st_ino


def read(path, limit=8 * 1024 * 1024):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Fichier ordinaire requis.")
        data = stream.read(limit + 1)
    require(len(data) <= limit, "Fichier trop volumineux.")
    return data


def document(raw):
    require(len(raw) <= 8 * 1024 * 1024, "JSON trop volumineux.")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "Champ JSON dupliqué.")
            value[key] = item
        return value
    def invalid(_value):
        raise Error("Nombre JSON non fini.")
    def finite(value):
        number = float(value)
        require(math.isfinite(number), "Nombre JSON non fini.")
        return number
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_constant=invalid, parse_float=finite)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise Error("JSON illisible.") from error
    require(isinstance(value, dict), "Objet JSON requis.")
    return value


class Evidence:
    def __init__(self, folder):
        self.folder = Path(folder)
        require(self.folder.is_dir() and not self.folder.is_symlink()
                and not any(self.folder.iterdir()), "Dossier de preuves neuf et vide requis.")
        self.files = {}
        self.sequence = 0
        self.stream = self._create("events.jsonl")

    def _create(self, name):
        require(Path(name).name == name, "Nom de preuve simple requis.")
        fd = os.open(self.folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            if os.geteuid() == 0:
                owner = self.folder.stat()
                os.fchown(fd, owner.st_uid, owner.st_gid)
            return os.fdopen(fd, "wb")
        except BaseException:
            os.close(fd)
            raise

    def save(self, name, data):
        if not isinstance(data, bytes):
            data = (json.dumps(data, ensure_ascii=False, allow_nan=False) + "\n").encode()
        with self._create(name) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        self.files[name] = digest(data)
        return data

    def record(self, state, **fields):
        self.sequence += 1
        value = {"sequence": self.sequence, "state": state,
                 "monotonic_ns": time.monotonic_ns(), **fields}
        self.stream.write((json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n").encode())
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def finish(self):
        if not self.stream.closed:
            self.stream.close()
            self.files["events.jsonl"] = digest(read(self.folder / "events.jsonl"))


class Tools:
    def __init__(self, paths):
        self.files, self.specs = {}, {}
        try:
            for name, path in paths.items():
                canonical = Path(path).resolve(strict=True)
                fd = os.open(canonical, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                self.files[name] = fd
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and info.st_mode & 0o111,
                        "Exécutable ordinaire requis.")
                data = self._bytes(fd)
                require(data.startswith(b"\x7fELF"), "Exécutable ELF requis.")
                self.specs[name] = {"path": str(canonical), "sha256": digest(data)}
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _bytes(fd):
        require(os.fstat(fd).st_size <= 64 * 1024 * 1024, "Exécutable trop volumineux.")
        data, offset = bytearray(), 0
        while True:
            block = os.pread(fd, 65536, offset)
            if not block:
                break
            data.extend(block)
            offset += len(block)
            require(offset <= 64 * 1024 * 1024, "Exécutable devenu trop volumineux.")
        return bytes(data)

    def verify(self, names=None):
        for name in names or self.files:
            fd, spec = self.files[name], self.specs[name]
            opened, current = os.fstat(fd), os.stat(spec["path"], follow_symlinks=False)
            require((opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino)
                    and digest(self._bytes(fd)) == spec["sha256"], "Exécutable modifié : " + name)

    def executable(self, name):
        return "/proc/self/fd/" + str(self.files[name])

    def close(self):
        for fd in self.files.values():
            os.close(fd)
        self.files.clear()


class Runner:
    def __init__(self, tools, evidence):
        self.tools, self.evidence, self.number = tools, evidence, 0

    def run(self, owner, tool, args, *, extra=(), timeout=6, allowed=(0,)):
        owner.check()
        require(0 < timeout <= 20, "Délai de commande invalide.")
        self.tools.verify((tool, *extra))
        self.number += 1
        number = self.number
        self.evidence.record("command_intent", command=number, tool=tool, arguments=args)
        group = guards.processes.ProcessGroup()
        owner.process_groups.append(group)
        output, errors, failure = bytearray(), bytearray(), None
        deadline = min(owner.deadline, time.monotonic() + timeout)
        child = None
        try:
            child = subprocess.Popen([self.tools.specs[tool]["path"], *args],
                executable=self.tools.executable(tool), pass_fds=tuple(self.tools.files.values()),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, env={"LANG":"C", "LC_ALL":"C", "PATH":os.pathsep.join(
                    dict.fromkeys(str(Path(self.tools.specs[key]["path"]).parent) for key in ("ip", "tc")))})
            group.attach(child)
            streams = [(child.stdout, output, 512 * 1024), (child.stderr, errors, 4096)]
            for stream, _data, _limit in streams:
                os.set_blocking(stream.fileno(), False)
            ended = set()
            while True:
                owner.check()
                require(time.monotonic() < deadline, "Délai de commande dépassé.")
                for stream, data, limit in streams:
                    if stream in ended:
                        continue
                    try:
                        block = os.read(stream.fileno(), min(16384, limit - len(data) + 1))
                        data.extend(block)
                        require(len(data) <= limit, "Sortie de commande trop volumineuse.")
                        if not block:
                            ended.add(stream)
                    except BlockingIOError:
                        pass
                if len(ended) == 2 and group.exited():
                    break
                time.sleep(.005)
        except BaseException as error:
            failure = error
        finally:
            try:
                group.stop(time.monotonic() + 3)
            except BaseException as error:
                failure = failure or error
            if child is not None and child.stderr is not None:
                child.stderr.close()
            self.evidence.save(f"command-{number:03d}.stdout", bytes(output))
            self.evidence.save(f"command-{number:03d}.stderr", bytes(errors))
            self.evidence.record("command_result", command=number, pid=child.pid if child else None,
                exit_code=group.driver_code, reaped_descendants=group.reaped_descendants,
                group_stopped=group.state == "stopped", error=str(failure) if failure else None)
        if failure is not None:
            raise failure
        self.tools.verify((tool, *extra))
        require(group.driver_code in allowed,
                f"Commande {tool} échouée ({group.driver_code}) : {bytes(errors)!r}")
        return bytes(output), group.driver_code


class Namespaces(guards.Namespaces):
    def __init__(self, runner):
        super().__init__(runner.tools.specs["ip"]["path"])
        self.runner, self.owner = runner, None

    def command(self, action, name, timeout):
        self.runner.run(self.owner, "ip", ["netns", action, name], timeout=timeout)


class RecoveryGuard(guards.Guard):
    def start_pinned_driver(self, tools, gateway, mode):
        self.check()
        require(self.process_group.state == "new" and self.child is None, "Pilote à usage unique requis.")
        tools.verify(("ip", "python"))
        self.child = subprocess.Popen([tools.specs["ip"]["path"], "netns", "exec", gateway,
            tools.executable("python"), "-I", "-c", driver_program(tools), mode],
            executable=tools.executable("ip"), pass_fds=tuple(tools.files.values()),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, start_new_session=True)
        os.set_blocking(self.child.stdout.fileno(), False)
        self.journal("running")
        self.check()


def driver_program(tools):
    # A Python started via /proc/self/fd/N can expose that path through
    # sys.executable. Its helper closes inherited FDs before exec, so point the
    # re-exec at the supervisor's retained descriptor instead of the child's.
    python = f"/proc/{os.getpid()}/fd/{tools.files['python']}"
    return "import sys\nsys.executable = " + repr(python) + "\n" + guards.WORKER
