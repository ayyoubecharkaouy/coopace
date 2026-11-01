"""One owned process group; no namespace ownership or resource deletion."""

import os
import signal
import subprocess
import time


class GroupError(Exception):
    pass


class ProcessGroup:
    """The caller launches an unreaped leader with start_new_session=True.

    Subreaper setup belongs to the supervisor. A failed stop is permanent:
    never signal a possibly reused process-group ID on a later call.
    """

    def __init__(self):
        self.child = None
        self.driver_code = None
        self.reaped_descendants = 0
        self.state = "new"
        self.failure = None
        self.leader_reaped = False

    def attach(self, child):
        if self.state != "new" or self.child is not None or child.returncode is not None:
            raise GroupError("Un leader neuf et non récupéré est requis.")
        self.child = child
        self.state = "running"

    def exited(self):
        if self.child is None:
            raise GroupError("Aucun leader enregistré.")
        if self.leader_reaped:
            return True
        return os.waitid(os.P_PID, self.child.pid,
                         os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None

    def _anchor(self):
        if self.child.returncode is not None:
            raise GroupError("Leader déjà récupéré avant les derniers signaux.")
        # Detect a wait performed outside this owner, without releasing PID.
        os.waitid(os.P_PID, self.child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)

    def stop(self, deadline):
        if self.failure is not None:
            raise GroupError("Arrêt du groupe précédemment non confirmé.") from self.failure
        if self.state == "stopped":
            return
        child = self.child
        if child is None:
            self.state = "stopped"
            return
        try:
            self.state = "stopping"
            try:
                self._anchor()
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                grace = min(deadline, time.monotonic() + 0.2)
                while time.monotonic() < grace:
                    time.sleep(0.01)
                self._anchor()
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.driver_code = child.wait(timeout=max(0.001, deadline - time.monotonic()))
                self.leader_reaped = True
                while True:
                    try:
                        pid, _status = os.waitpid(-child.pid, os.WNOHANG)
                    except ChildProcessError:
                        break
                    if pid:
                        self.reaped_descendants += 1
                    elif time.monotonic() >= deadline:
                        raise GroupError("Arrêt des descendants non confirmé.")
                    else:
                        time.sleep(0.01)
            finally:
                # stderr belongs to the caller, which may drain it after wait.
                for stream in (child.stdout, child.stdin):
                    if stream is not None:
                        stream.close()
            self.state = "stopped"
        except BaseException as error:
            self.state, self.failure = "failed", error
            raise

    def require_stopped(self):
        if self.state != "stopped" or self.failure is not None:
            raise GroupError("Groupe non récupéré ; transition interdite.")
