//go:build linux && !android

package labcontrol

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/snapshot"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

const gatewaySessionFrameLimit = 16384

// Every field is required, including the consent assertion. This protocol is
// private to a trusted owned-lab launcher; JSON alone grants no OS authority.
type gatewaySessionInit struct {
	Schema      *int                  `json:"schema_version"`
	Kind        *string               `json:"kind"`
	Session     *string               `json:"session_id"`
	Scope       *string               `json:"scope"`
	Reference   *core.CakeReferenceID `json:"reference"`
	BeforePath  *string               `json:"before_path"`
	BeforeSHA   *string               `json:"before_sha256"`
	Consent     *bool                 `json:"local_lab_consent"`
	OperatorUID *int                  `json:"operator_uid"`
	Namespace   *struct {
		Device *uint64 `json:"device"`
		Inode  *uint64 `json:"inode"`
	} `json:"namespace_identity"`
}

type gatewaySessionCommand struct {
	Schema       *int    `json:"schema_version"`
	Kind         *string `json:"kind"`
	Session      *string `json:"session_id"`
	Sequence     *uint64 `json:"sequence"`
	Action       *string `json:"action"`
	BeforeSHA    *string `json:"before_sha256"`
	SnapshotPath string  `json:"snapshot_path,omitempty"`
	SnapshotSHA  string  `json:"snapshot_sha256,omitempty"`
}

type gatewaySessionEvent struct {
	Schema      int    `json:"schema_version"`
	Kind        string `json:"kind"`
	Session     string `json:"session_id"`
	Sequence    uint64 `json:"sequence"`
	Phase       string `json:"phase"`
	BeforeSHA   string `json:"before_sha256"`
	SnapshotSHA string `json:"snapshot_sha256,omitempty"`
}

func readSessionSnapshot(ctx context.Context, path, sha string) (snapshot.Imported, error) {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path || len(path) > 4096 {
		return snapshot.Imported{}, fmt.Errorf("absolute clean snapshot path required")
	}
	fd, err := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK|syscall.O_CLOEXEC, 0)
	if err != nil {
		return snapshot.Imported{}, err
	}
	file := os.NewFile(uintptr(fd), "session-snapshot")
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return snapshot.Imported{}, err
	}
	if !info.Mode().IsRegular() || info.Size() > snapshot.MaxImportBytes {
		return snapshot.Imported{}, fmt.Errorf("bounded regular snapshot required")
	}
	imported, err := snapshot.Read(ctx, file)
	if err != nil {
		return snapshot.Imported{}, err
	}
	if imported.SHA256 != sha {
		return snapshot.Imported{}, fmt.Errorf("snapshot SHA-256 mismatch")
	}
	return imported, nil
}

func sessionApplied(before, applied snapshot.Imported) error {
	b, a := before.Snapshot, applied.Snapshot
	if a.Partial() || a.Interface != b.Interface || !a.StartedAt.After(b.FinishedAt) {
		return fmt.Errorf("complete later snapshot of the same lab link required")
	}
	for _, reading := range a.Readings[2:] {
		var rows []json.RawMessage
		if json.Unmarshal(reading.Value, &rows) != nil || len(rows) != 0 {
			return fmt.Errorf("classes or filters present")
		}
	}
	if _, err := linux.ParseCakeReading(a.Readings[1].Value, linux.CakeIPRoute2V610); err != nil {
		return err
	}
	return nil
}

func (t *WorkerTransport) readSessionFrame(ctx context.Context, value any) error {
	return t.withDeadline(ctx, t.control, time.Now().Add(25*time.Second), false, func() error {
		data, err := readFrame(t.control, gatewaySessionFrameLimit)
		if err != nil {
			return err
		}
		var fields map[string]json.RawMessage
		if err := json.Unmarshal(data, &fields); err != nil || fields == nil {
			return fmt.Errorf("session object required")
		}
		for _, raw := range fields {
			if strings.TrimSpace(string(raw)) == "null" {
				return fmt.Errorf("null session field")
			}
		}
		return decode(data, value)
	})
}

func (t *WorkerTransport) sendSessionEvent(ctx context.Context, value gatewaySessionEvent) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	if len(data) > gatewaySessionFrameLimit || t.written+len(data)+4 > 65536 {
		return fmt.Errorf("session event budget exceeded")
	}
	frame := make([]byte, 4, len(data)+4)
	binary.BigEndian.PutUint32(frame, uint32(len(data)))
	frame = append(frame, data...)
	return t.withDeadline(ctx, t.events, time.Now().Add(5*time.Second), true, func() error {
		for len(frame) > 0 {
			n, err := t.events.Write(frame)
			t.written += n
			frame = frame[n:]
			if err != nil {
				return err
			}
			if n == 0 {
				return io.ErrShortWrite
			}
		}
		return nil
	})
}

type sessionJournal interface{ Record(string, any) error }

// The injected boundary is only used by tests. The executable always uses
// VerifyLabNamespace and the real UID, never a flag to bypass namespace checks.
func runGatewaySession(ctx context.Context, transport *WorkerTransport, journal sessionJournal, session string, uid int,
	verify func(linux.NetworkNamespaceIdentity) error) error {
	var init gatewaySessionInit
	if err := transport.readSessionFrame(ctx, &init); err != nil {
		return err
	}
	if init.Schema == nil || *init.Schema != 1 || init.Kind == nil || *init.Kind != "gateway_session_init" ||
		init.Session == nil || *init.Session != session || init.Scope == nil || *init.Scope != "owned_lab" ||
		init.Reference == nil || init.BeforePath == nil || init.BeforeSHA == nil || init.Consent == nil ||
		init.OperatorUID == nil || *init.OperatorUID != uid || uid <= 0 || init.Namespace == nil ||
		init.Namespace.Device == nil || init.Namespace.Inode == nil {
		return fmt.Errorf("invalid gateway session initialization")
	}
	state, err := core.NewGatewaySession(*init.Reference, *init.BeforeSHA, *init.Consent)
	if err != nil {
		return err
	}
	identity := linux.NetworkNamespaceIdentity{Device: *init.Namespace.Device, Inode: *init.Namespace.Inode}
	if err := verify(identity); err != nil {
		return err
	}
	before, err := readSessionSnapshot(ctx, *init.BeforePath, *init.BeforeSHA)
	if err != nil {
		return err
	}
	assessment, err := linux.AssessQueueRecovery(before.Snapshot)
	if err != nil {
		return err
	}
	if !assessment.Candidate || before.Snapshot.Interface.Name != "wan" {
		return fmt.Errorf("lab wan noqueue baseline required")
	}
	var links []struct {
		LinkInfo struct {
			Kind string `json:"info_kind"`
		} `json:"linkinfo"`
	}
	if json.Unmarshal(before.Snapshot.Readings[0].Value, &links) != nil || len(links) != 1 || links[0].LinkInfo.Kind != "veth" {
		return fmt.Errorf("owned lab veth baseline required")
	}
	emit := func(sequence uint64, sha string) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		if err := verify(identity); err != nil {
			return err
		}
		event := gatewaySessionEvent{1, "gateway_session_event", session, sequence, state.Phase(), *init.BeforeSHA, sha}
		if err := journal.Record(state.Phase(), event); err != nil {
			return err
		}
		return transport.sendSessionEvent(ctx, event)
	}
	if err := emit(1, ""); err != nil {
		return err
	}
	for sequence := uint64(1); sequence <= 3; sequence++ {
		var command gatewaySessionCommand
		if err := transport.readSessionFrame(ctx, &command); err != nil {
			return err
		}
		if command.Schema == nil || *command.Schema != 1 || command.Kind == nil || *command.Kind != "gateway_session_command" ||
			command.Session == nil || *command.Session != session || command.Sequence == nil || command.Action == nil || command.BeforeSHA == nil {
			return fmt.Errorf("invalid gateway session command")
		}
		if err := verify(identity); err != nil {
			return err
		}
		if err := state.Advance(*command.Sequence, *command.Action, *command.BeforeSHA); err != nil {
			return err
		}
		sha := ""
		if state.Phase() == "applied" {
			applied, err := readSessionSnapshot(ctx, command.SnapshotPath, command.SnapshotSHA)
			if err != nil {
				return err
			}
			if err := sessionApplied(before, applied); err != nil {
				return err
			}
			sha = applied.SHA256
		} else if command.SnapshotPath != "" || command.SnapshotSHA != "" {
			return fmt.Errorf("unexpected snapshot in command")
		}
		if err := emit(sequence+1, sha); err != nil {
			return err
		}
	}
	return nil // release requested; the supervisor must stop this group and restore.
}

// RunGatewaySessionWorker is the private unprivileged decision process. It has
// no command runner, never enters a namespace and cannot install/remove a queue.
func RunGatewaySessionWorker(parent context.Context, args []string, started time.Time, stderr io.Writer) int {
	if len(args) == 1 && args[0] == "--help" {
		fmt.Fprintln(stderr, "Coopace : pilote interne de session ; lanceur supervisé requis. FDs 3..7 ; --session-id IDENTIFIANT.")
		return 0
	}
	if len(args) != 2 || args[0] != "--session-id" || !validSession(args[1]) {
		fmt.Fprintln(stderr, "invalid internal session launch")
		return 2
	}
	// Dropping UID in the single-threaded bootstrap also clears effective
	// capabilities. Refuse inherited ambient authority before opening the pipes.
	status, err := os.ReadFile("/proc/self/status")
	capsOK := false
	for _, line := range strings.Split(string(status), "\n") {
		fields := strings.Fields(line)
		if len(fields) == 2 && fields[0] == "CapEff:" {
			capsOK = fields[1] == "0000000000000000"
		}
	}
	if err != nil || os.Getuid() <= 0 || os.Geteuid() != os.Getuid() || !capsOK {
		fmt.Fprintln(stderr, "unprivileged session worker required")
		return 1
	}
	journal, err := openInheritedJournal(args[1], started)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	journal.kind = "gateway_session_worker_journal"
	transport, err := OpenInheritedTransport()
	if err != nil {
		journal.Close()
		fmt.Fprintln(stderr, err)
		return 1
	}
	ctx, cancel := context.WithDeadline(parent, started.Add(90*time.Second))
	defer cancel()
	ctx, stop := watchWorkerSignals(ctx)
	defer stop()
	err = journal.Record("launch", map[string]any{"operator_uid": os.Getuid(), "network_changes_executed": false})
	if err == nil {
		err = runGatewaySession(ctx, transport, journal, args[1], os.Getuid(), func(identity linux.NetworkNamespaceIdentity) error {
			return linux.VerifyLabNamespace(identity, transport.target, transport.original)
		})
	}
	exit := map[string]any{"awaiting_supervisor_recovery": true, "succeeded": err == nil}
	if err != nil {
		exit["error"] = err.Error()
	}
	err = errors.Join(err, journal.Record("worker_exit", exit), journal.Close(), transport.Close())
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return 0
}
