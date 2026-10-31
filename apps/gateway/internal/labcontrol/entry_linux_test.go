//go:build linux && !android

package labcontrol

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

func workerTestArgs() []string {
	return []string{"--session-id", "abcd1234", "--ip", "/missing/ip", "--ip-sha256", strings.Repeat("0", 64), "--tc", "/missing/tc", "--tc-sha256", strings.Repeat("0", 64)}
}

func TestWorkerLaunchRejectsUnknownDuplicateIncompleteAndUnboundedOptions(t *testing.T) {
	if _, err := parseWorkerLaunch(workerTestArgs()); err != nil {
		t.Fatal(err)
	}
	for _, mode := range []string{"missing", "duplicate", "unknown", "scenario", "relative", "hash", "session", "oversize", "extra"} {
		args := workerTestArgs()
		switch mode {
		case "missing":
			args = args[:8]
		case "duplicate":
			args[2] = "--tc"
		case "unknown":
			args[0] = "--execute"
		case "scenario":
			args[0] = "--scenario"
		case "relative":
			args[3] = "tc"
		case "hash":
			args[5] = "invalid"
		case "session":
			args[1] = "ABCD1234"
		case "oversize":
			args[3] = "/" + strings.Repeat("x", 4097)
		case "extra":
			args = append(args, "--apply")
		}
		if _, err := parseWorkerLaunch(args); err == nil {
			t.Fatal("invalid launch accepted", mode)
		}
	}
}

func testRecordedWorker(ctx context.Context, transport *WorkerTransport, session string, started time.Time, _ nativeTools, journal *workerJournal) (linux.CakeLabEvidence, error) {
	mode := os.Getenv("COOPACE_LAB_TRANSPORT_HELPER")
	var forbidden []string
	for _, file := range []*os.File{transport.control, transport.events, transport.target, transport.original, journal.file} {
		info, err := file.Stat()
		if err != nil {
			return linux.CakeLabEvidence{}, err
		}
		stat := info.Sys().(*syscall.Stat_t)
		forbidden = append(forbidden, fmt.Sprintf("%d:%d", stat.Dev, stat.Ino))
	}
	path, _ := os.Executable()
	binary, _ := os.ReadFile(path)
	hash := sha256.Sum256(binary)
	tool := linux.LabToolSpec{Path: path, SHA256: hex.EncodeToString(hash[:])}
	phase := func(ctx context.Context, name string) ([]byte, error) {
		args := []string{"-test.run=^TestTransportToolHelper$", "--", name}
		if err := journal.ToolIntent(tool, args); err != nil {
			return nil, err
		}
		command := exec.CommandContext(ctx, path, args...)
		command.WaitDelay = 100 * time.Millisecond
		command.Env = append(os.Environ(), "COOPACE_LAB_TOOL=1", "COOPACE_LAB_FORBIDDEN_FDS="+strings.Join(forbidden, ","), "GORACE=atexit_sleep_ms=0")
		start := time.Now()
		raw, err := command.Output()
		call := linux.LabToolCall{Path: path, SHA256: tool.SHA256, Arguments: args, StartedAt: start.UTC(), Duration: time.Since(start), Stdout: raw}
		if command.Process != nil {
			call.PID = command.Process.Pid
		}
		if command.ProcessState != nil {
			code := command.ProcessState.ExitCode()
			call.ExitCode = &code
		}
		if err != nil {
			call.Error = err.Error()
		}
		err = errors.Join(err, journal.ToolResult(call))
		return raw, err
	}
	add := false
	operations := workerOperations{
		initial: func(ctx context.Context) ([]byte, error) { return phase(ctx, "initial") },
		apply: func(ctx context.Context) ([]byte, linux.CakeProducerProfile, error) {
			add = true
			raw, err := phase(ctx, "apply")
			return raw, linux.CakeIPRoute2V610, err
		},
		final: func(ctx context.Context) ([]byte, error) { return phase(ctx, "final") },
		verify: func(expected linux.NetworkNamespaceIdentity, target, original *os.File) error {
			for _, file := range []*os.File{target, original} {
				info, err := file.Stat()
				if err != nil {
					return err
				}
				stat := info.Sys().(*syscall.Stat_t)
				if expected != (linux.NetworkNamespaceIdentity{Device: uint64(stat.Dev), Inode: uint64(stat.Ino)}) {
					return errors.New("inherited identity mismatch")
				}
			}
			return nil // Positive namespace distinction is explicitly simulated.
		},
		record: func(event string, data any) error {
			if mode == "entry_journal_failure" && event == "apply_received" {
				journal.sync = func() error { return errors.New("simulated fsync failure") }
			}
			return journal.Record(event, data)
		},
	}
	err := runWorker(ctx, transport, session, started, operations)
	state := "finished"
	if err != nil {
		state = "failed"
	}
	return linux.CakeLabEvidence{State: state, AddAttempted: add}, err
}

func eventNames(rows []map[string]json.RawMessage) []string {
	var result []string
	for _, row := range rows {
		var event string
		json.Unmarshal(row["event"], &event)
		result = append(result, event)
	}
	return result
}

func TestWorkerEntryPersistsToolsAndPhasesBeforeEvents(t *testing.T) {
	h := startWorkerProcess(t, "entry_flow")
	h.request(t, "abcd1234")
	h.event(t, "ready")
	rows := journalRecords(t, h.journal)
	if names := eventNames(rows); names[len(names)-1] != "ready" {
		t.Fatal("ready emitted before durable record", names)
	}
	h.send(t, "apply")
	h.event(t, "applied")
	rows = journalRecords(t, h.journal)
	names := eventNames(rows)
	if names[len(names)-1] != "applied" || names[len(names)-2] != "tool_result" {
		t.Fatal("applied emitted before durable tool result", names)
	}
	h.send(t, "finish")
	if err := h.wait(); err != nil {
		t.Fatal(err, h.stderr.String())
	}
	rows = journalRecords(t, h.journal)
	names = eventNames(rows)
	if names[len(names)-2] != "final_verified" || names[len(names)-1] != "worker_exit" {
		t.Fatal("completion not recorded", names)
	}
	var exit struct {
		Code    int    `json:"intended_exit_code"`
		Cleanup string `json:"cleanup"`
	}
	if err := json.Unmarshal(rows[len(rows)-1]["data"], &exit); err != nil || exit.Code != 0 || exit.Cleanup != "not_attested" {
		t.Fatal("incorrect exit record", err)
	}
	if h.toolCalls() != "initial\napply\nfinal\n" {
		t.Fatal("incorrect tool sequence", h.toolCalls())
	}
}

func TestWorkerEntryRefusalsSignalsAndKilledPrefix(t *testing.T) {
	for _, mode := range []string{"entry_native", "entry_wrong_session", "entry_journal_failure", "entry_signal", "entry_sigint", "entry_sighup", "entry_kill", "entry_populated_journal", "entry_badmode_journal", "entry_readonly_journal", "entry_missing_journal"} {
		t.Run(mode, func(t *testing.T) {
			h := startWorkerProcess(t, mode)
			if mode == "entry_populated_journal" || mode == "entry_badmode_journal" || mode == "entry_readonly_journal" || mode == "entry_missing_journal" {
				if err := h.wait(); err == nil || h.command.ProcessState.ExitCode() != 2 {
					t.Fatal("nonempty journal accepted")
				}
				raw, _ := os.ReadFile(h.journal)
				expected := ""
				if mode == "entry_populated_journal" {
					expected = "existing evidence"
				}
				if string(raw) != expected {
					t.Fatal("existing evidence changed")
				}
				return
			}
			session := "abcd1234"
			if mode == "entry_wrong_session" {
				session = "other123"
			}
			h.request(t, session)
			switch mode {
			case "entry_native", "entry_wrong_session":
				if err := h.wait(); err == nil || h.command.ProcessState.ExitCode() != 2 {
					t.Fatal("invalid context accepted", h.stderr.String())
				}
				if h.toolCalls() != "" {
					t.Fatal("tool ran before context validation")
				}
			case "entry_journal_failure":
				h.event(t, "ready")
				h.send(t, "apply")
				if err := h.wait(); err == nil {
					t.Fatal("failed journal reported success")
				}
				if h.toolCalls() != "initial\n" {
					t.Fatal("tool ran after journal failure")
				}
			case "entry_signal", "entry_sigint", "entry_sighup":
				value := syscall.SIGTERM
				if mode == "entry_sigint" {
					value = syscall.SIGINT
				}
				if mode == "entry_sighup" {
					value = syscall.SIGHUP
				}
				h.event(t, "ready")
				h.command.Process.Signal(value)
				if err := h.wait(); err == nil || h.command.ProcessState.ExitCode() != 128+int(value) {
					t.Fatal("signal not handled", h.stderr.String())
				}
			case "entry_kill":
				h.event(t, "ready")
				h.send(t, "apply")
				h.event(t, "applied")
				syscall.Kill(-h.command.Process.Pid, syscall.SIGKILL)
				if err := h.wait(); err == nil {
					t.Fatal("forced termination succeeded")
				}
			}
			rows := journalRecords(t, h.journal)
			names := eventNames(rows)
			if mode == "entry_kill" {
				if names[len(names)-1] != "applied" {
					t.Fatal("durable prefix missing", names)
				}
			} else if mode != "entry_journal_failure" && names[len(names)-1] != "worker_exit" {
				t.Fatal("failure not recorded", names)
			}
		})
	}
}

func TestCompiledInternalWorkerHelpAndNativeRefusal(t *testing.T) {
	binary := filepath.Join(t.TempDir(), "coopace-cake-worker")
	script, err := filepath.Abs("../../../../scripts/go.sh")
	if err != nil {
		t.Fatal(err)
	}
	build := exec.Command("sh", script, "build", "-o", binary, "./apps/gateway/cmd/coopace-cake-worker")
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatal(err, string(output))
	}
	var stdout, stderr bytes.Buffer
	help := exec.Command(binary, "--help")
	help.Stdout = &stdout
	help.Stderr = &stderr
	if err := help.Run(); err != nil || stdout.Len() != 0 || !strings.Contains(stderr.String(), "processus interne") {
		t.Fatal("compiled help failed", err)
	}
	h := startWorkerProgram(t, "entry_native", binary)
	h.request(t, "abcd1234")
	if err := h.wait(); err == nil || h.command.ProcessState.ExitCode() != 2 {
		t.Fatal("compiled worker accepted original namespace", h.stderr.String())
	}
	rows := journalRecords(t, h.journal)
	if len(rows) != 2 || eventNames(rows)[1] != "worker_exit" {
		t.Fatal("compiled refusal was not journaled")
	}
}
