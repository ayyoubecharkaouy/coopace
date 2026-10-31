//go:build linux && !android

package labcontrol

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"syscall"
	"time"

	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

const (
	JournalFD             = 7
	MaxJournalBytes       = 8 * 1024 * 1024
	MaxJournalRecordBytes = 256 * 1024
)

// The launcher creates this file exclusively outside its disposable workspace,
// syncs its directory, and passes only its append-only writer. The worker never
// receives an evidence pathname and cannot prove the launcher's creation history.
type workerJournal struct {
	file       *os.File
	identity   syscall.Stat_t
	session    string
	started    time.Time
	sequence   uint64
	written    int64
	failure    error
	closed     bool
	closeError error
	sync       func() error
}

func openInheritedJournal(session string, started time.Time) (journal *workerJournal, result error) {
	var file *os.File
	defer func() {
		if result != nil {
			if file != nil {
				file.Close()
			} else {
				syscall.Close(JournalFD)
			}
		}
	}()
	if !validSession(session) || started.IsZero() || started.After(time.Now()) {
		return nil, fmt.Errorf("invalid journal launch")
	}
	var stat syscall.Stat_t
	if err := syscall.Fstat(JournalFD, &stat); err != nil {
		return nil, err
	}
	flags, _, errno := syscall.Syscall(syscall.SYS_FCNTL, JournalFD, syscall.F_GETFL, 0)
	if errno != 0 || stat.Mode&syscall.S_IFMT != syscall.S_IFREG || stat.Mode&07777 != 0600 || stat.Nlink != 1 || stat.Size != 0 ||
		int(flags)&syscall.O_ACCMODE != syscall.O_WRONLY || flags&syscall.O_APPEND == 0 || flags&syscall.O_NONBLOCK != 0 {
		return nil, fmt.Errorf("FD 7 requires an empty private regular append-only journal")
	}
	syscall.CloseOnExec(JournalFD)
	fdFlags, _, errno := syscall.Syscall(syscall.SYS_FCNTL, JournalFD, syscall.F_GETFD, 0)
	if errno != 0 || fdFlags&syscall.FD_CLOEXEC == 0 {
		return nil, fmt.Errorf("journal must be close-on-exec")
	}
	file = os.NewFile(JournalFD, "inherited-worker-journal")
	if file == nil {
		return nil, fmt.Errorf("journal descriptor unavailable")
	}
	return &workerJournal{file: file, identity: stat, session: session, started: started, sync: file.Sync}, nil
}

func (j *workerJournal) fail(err error) error {
	if j.failure == nil {
		j.failure = err
	}
	return j.failure
}

func (j *workerJournal) Record(event string, data any) error {
	if j.failure != nil {
		return j.failure
	}
	if j.closed || j.file == nil {
		return j.fail(fmt.Errorf("worker journal is closed"))
	}
	switch event {
	case "launch", "context_accepted", "tool_intent", "tool_result", "ready", "apply_received", "applied", "finish_received", "final_verified", "worker_exit":
	default:
		return j.fail(fmt.Errorf("unknown worker journal event"))
	}
	info, err := j.file.Stat()
	if err != nil {
		return j.fail(err)
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	flags, _, errno := syscall.Syscall(syscall.SYS_FCNTL, j.file.Fd(), syscall.F_GETFL, 0)
	if !ok || stat.Dev != j.identity.Dev || stat.Ino != j.identity.Ino || stat.Nlink != 1 || stat.Mode&07777 != 0600 || stat.Size != j.written || errno != 0 || flags&syscall.O_APPEND == 0 {
		return j.fail(fmt.Errorf("worker journal identity, permissions or size changed"))
	}
	now := time.Now()
	value := struct {
		Schema     int       `json:"schema_version"`
		Kind       string    `json:"kind"`
		Session    string    `json:"session_id"`
		Sequence   uint64    `json:"sequence"`
		Event      string    `json:"event"`
		RecordedAt time.Time `json:"recorded_at"`
		ElapsedNS  int64     `json:"elapsed_ns"`
		Data       any       `json:"data"`
	}{1, "lab_cake_worker_journal", j.session, j.sequence + 1, event, now.UTC(), now.Sub(j.started).Nanoseconds(), data}
	encoded, err := json.Marshal(value)
	if err != nil {
		return j.fail(err)
	}
	encoded = append(encoded, '\n')
	if len(encoded) > MaxJournalRecordBytes || int64(len(encoded)) > MaxJournalBytes-j.written {
		return j.fail(fmt.Errorf("worker journal budget exceeded"))
	}
	for len(encoded) > 0 {
		n, err := j.file.Write(encoded)
		j.written += int64(n)
		encoded = encoded[n:]
		if err != nil {
			return j.fail(err)
		}
		if n == 0 {
			return j.fail(fmt.Errorf("worker journal write made no progress"))
		}
	}
	if err := j.sync(); err != nil {
		return j.fail(err)
	}
	j.sequence++
	return nil
}

func (j *workerJournal) ToolIntent(tool linux.LabToolSpec, args []string) error {
	return j.Record("tool_intent", struct {
		Path      string   `json:"path"`
		SHA256    string   `json:"sha256"`
		Arguments []string `json:"arguments"`
	}{tool.Path, tool.SHA256, args})
}

func (j *workerJournal) ToolResult(call linux.LabToolCall) error {
	return j.Record("tool_result", struct {
		Path            string    `json:"path"`
		SHA256          string    `json:"sha256"`
		Arguments       []string  `json:"arguments"`
		StartedAt       time.Time `json:"started_at"`
		DurationNS      int64     `json:"duration_ns"`
		PID             int       `json:"pid"`
		ExitCode        *int      `json:"exit_code"`
		Stdout          []byte    `json:"stdout_base64"`
		Stderr          []byte    `json:"stderr_base64"`
		StdoutTruncated bool      `json:"stdout_truncated"`
		StderrTruncated bool      `json:"stderr_truncated"`
		Error           string    `json:"error"`
	}{call.Path, call.SHA256, call.Arguments, call.StartedAt, call.Duration.Nanoseconds(), call.PID, call.ExitCode, call.Stdout, call.Stderr, call.StdoutTruncated, call.StderrTruncated, call.Error})
}

func (j *workerJournal) Close() error {
	if j.closed {
		return j.closeError
	}
	j.closed = true
	if j.file != nil {
		j.closeError = errors.Join(j.failure, j.sync(), j.file.Close())
	}
	return j.closeError
}
