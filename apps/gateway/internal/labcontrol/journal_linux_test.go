//go:build linux && !android

package labcontrol

import (
	"bytes"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/internal/strictjson"
	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

func testJournal(t *testing.T) (*workerJournal, string) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "worker.jsonl")
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL|os.O_APPEND, 0600)
	if err != nil {
		t.Fatal(err)
	}
	info, _ := file.Stat()
	stat := info.Sys().(*syscall.Stat_t)
	j := &workerJournal{file: file, identity: *stat, session: "abcd1234", started: time.Now(), sync: file.Sync}
	t.Cleanup(func() { j.Close() })
	return j, path
}

func journalRecords(t *testing.T, path string) []map[string]json.RawMessage {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(raw) > 0 && raw[len(raw)-1] != '\n' {
		t.Fatal("journal ends in a partial record")
	}
	var result []map[string]json.RawMessage
	for i, line := range bytes.Split(bytes.TrimSpace(raw), []byte("\n")) {
		if len(line) == 0 {
			continue
		}
		if err := strictjson.Check(line, MaxJournalRecordBytes); err != nil {
			t.Fatal(err)
		}
		var record map[string]json.RawMessage
		if err := json.Unmarshal(line, &record); err != nil {
			t.Fatal(err)
		}
		var sequence uint64
		json.Unmarshal(record["sequence"], &sequence)
		if sequence != uint64(i+1) || string(record["session_id"]) != `"abcd1234"` || string(record["kind"]) != `"lab_cake_worker_journal"` {
			t.Fatal("journal identity/order changed")
		}
		result = append(result, record)
	}
	return result
}

func TestJournalSyncsEveryRecordAndPreservesExactSourceBytes(t *testing.T) {
	j, path := testJournal(t)
	syncs := 0
	j.sync = func() error { syncs++; return j.file.Sync() }
	if err := j.Record("launch", nil); err != nil {
		t.Fatal(err)
	}
	tool := linux.LabToolSpec{Path: "/tools/tc", SHA256: strings.Repeat("a", 64)}
	if err := j.ToolIntent(tool, []string{"-V"}); err != nil {
		t.Fatal(err)
	}
	code := 7
	source := []byte{0, 255, 128, '\n'}
	if err := j.ToolResult(linux.LabToolCall{Path: tool.Path, SHA256: tool.SHA256, Arguments: []string{"-V"}, Stdout: source, Stderr: source, ExitCode: &code, Error: "failure"}); err != nil {
		t.Fatal(err)
	}
	if syncs != 3 {
		t.Fatal("records were not individually synced")
	}
	rows := journalRecords(t, path)
	var call struct {
		Stdout   []byte `json:"stdout_base64"`
		Stderr   []byte `json:"stderr_base64"`
		ExitCode *int   `json:"exit_code"`
	}
	if err := json.Unmarshal(rows[2]["data"], &call); err != nil || !bytes.Equal(call.Stdout, source) || !bytes.Equal(call.Stderr, source) || call.ExitCode == nil || *call.ExitCode != 7 {
		t.Fatal("source bytes/code lost", err)
	}
	if info, err := os.Stat(path); err != nil || info.Mode().Perm() != 0600 {
		t.Fatal("journal not private")
	}
}

func TestJournalRefusesOverflowAndRemainsFailed(t *testing.T) {
	for _, mode := range []string{"record", "total", "sync", "tamper", "unknown", "append_flag"} {
		t.Run(mode, func(t *testing.T) {
			j, path := testJournal(t)
			var err error
			switch mode {
			case "record":
				err = j.Record("ready", strings.Repeat("x", MaxJournalRecordBytes))
			case "total":
				for i := 0; i < 50; i++ {
					err = j.Record("ready", strings.Repeat("x", 240*1024))
					if err != nil {
						break
					}
				}
			case "sync":
				j.sync = func() error { return errors.New("sync failed") }
				err = j.Record("ready", nil)
			case "tamper":
				os.WriteFile(path, []byte("external"), 0600)
				err = j.Record("ready", nil)
			case "unknown":
				err = j.Record("cleanup_verified", nil)
			case "append_flag":
				_, _, errno := syscall.Syscall(syscall.SYS_FCNTL, j.file.Fd(), syscall.F_SETFL, syscall.O_WRONLY)
				if errno != 0 {
					t.Fatal(errno)
				}
				err = j.Record("ready", nil)
			}
			if err == nil {
				t.Fatal("invalid journal continued")
			}
			before, _ := os.ReadFile(path)
			if err := j.Record("applied", nil); err == nil {
				t.Fatal("failed journal resumed")
			}
			after, _ := os.ReadFile(path)
			if !bytes.Equal(before, after) {
				t.Fatal("failed journal appended more data")
			}
			if len(after) > MaxJournalBytes {
				t.Fatal("journal exceeded total budget")
			}
		})
	}
}
