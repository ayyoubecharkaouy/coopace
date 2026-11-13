//go:build linux && !android

package labcontrol

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/snapshot"
	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

type sessionMemoryJournal struct {
	events []string
	fail   string
}

func (j *sessionMemoryJournal) Record(event string, _ any) error {
	if event == j.fail {
		return errors.New("journal unavailable")
	}
	j.events = append(j.events, event)
	return nil
}

func sessionSnapshots(t *testing.T) (before, applied, path, appliedPath string) {
	t.Helper()
	raw, err := os.ReadFile("../../../../docs/examples/queue-snapshot-noqueue.json")
	if err != nil {
		t.Fatal(err)
	}
	raw = bytes.ReplaceAll(raw, []byte("lab0"), []byte("wan"))
	raw = bytes.Replace(raw, []byte(`"link_type": "ether"`), []byte(`"link_type": "ether", "linkinfo":{"info_kind":"veth"}`), 1)
	dir := t.TempDir()
	path = filepath.Join(dir, "before.json")
	appliedPath = filepath.Join(dir, "applied.json")
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	before = fmt.Sprintf("%x", sha256.Sum256(raw))
	imported, err := snapshot.Read(context.Background(), bytes.NewReader(raw))
	if err != nil {
		t.Fatal(err)
	}
	s := imported.Snapshot
	s.StartedAt = s.StartedAt.Add(2 * time.Second)
	s.FinishedAt = s.FinishedAt.Add(2 * time.Second)
	for i := range s.Readings {
		r := &s.Readings[i]
		r.StartedAt = r.StartedAt.Add(2 * time.Second)
		r.FinishedAt = r.FinishedAt.Add(2 * time.Second)
		if f := r.ClassesTextFallback; f != nil {
			f.StartedAt = f.StartedAt.Add(2 * time.Second)
			f.FinishedAt = f.FinishedAt.Add(2 * time.Second)
		}
	}
	cake, err := os.ReadFile("../../../../platforms/linux/testdata/cake/down.json")
	if err != nil {
		t.Fatal(err)
	}
	s.Readings[1].Value = cake
	s.Readings[0].Value = bytes.Replace(s.Readings[0].Value, []byte(`"noqueue"`), []byte(`"cake"`), 1)
	var buf bytes.Buffer
	if err := snapshot.WriteJSON(&buf, snapshot.Report{Version: "simulated", OS: "linux", Architecture: "amd64", Snapshot: s}); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(appliedPath, buf.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}
	applied = fmt.Sprintf("%x", sha256.Sum256(buf.Bytes()))
	return
}

func TestGatewaySessionDialogueWithRealPipesAndSimulatedNamespace(t *testing.T) {
	for _, scenario := range []string{"normal", "consent_missing", "consent_false", "wrong_session", "wrong_sha", "duplicate", "wrong_namespace", "namespace_lost", "applied_wrong_sha", "applied_reused_before", "journal_failure", "cancel", "eof", "unknown_field", "case_alias", "null_field", "wrong_sequence"} {
		t.Run(scenario, func(t *testing.T) {
			before, applied, path, appliedPath := sessionSnapshots(t)
			cr, cw, err := os.Pipe()
			if err != nil {
				t.Fatal(err)
			}
			defer cr.Close()
			defer cw.Close()
			er, ew, err := os.Pipe()
			if err != nil {
				t.Fatal(err)
			}
			defer er.Close()
			defer ew.Close()
			if err := er.SetReadDeadline(time.Now().Add(3 * time.Second)); err != nil {
				t.Fatal(err)
			}
			transport := &WorkerTransport{control: cr, events: ew}
			journal := &sessionMemoryJournal{}
			if scenario == "journal_failure" {
				journal.fail = "apply_requested"
			}
			ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			verified := 0
			verify := func(got linux.NetworkNamespaceIdentity) error {
				verified++
				if got != (linux.NetworkNamespaceIdentity{Device: 1, Inode: 2}) || scenario == "wrong_namespace" || (scenario == "namespace_lost" && verified > 2) {
					return errors.New("namespace changed")
				}
				return nil
			}
			done := make(chan error, 1)
			go func() { defer ew.Close(); done <- runGatewaySession(ctx, transport, journal, "session1", 1000, verify) }()
			init := map[string]any{"schema_version": 1, "kind": "gateway_session_init", "session_id": "session1", "scope": "owned_lab",
				"reference": "cake-ipv4-lab-4mbit-v1", "before_path": path, "before_sha256": before, "local_lab_consent": true,
				"operator_uid": 1000, "namespace_identity": map[string]any{"device": 1, "inode": 2}}
			switch scenario {
			case "consent_missing":
				delete(init, "local_lab_consent")
			case "consent_false":
				init["local_lab_consent"] = false
			case "wrong_session":
				init["session_id"] = "session2"
			case "wrong_sha":
				init["before_sha256"] = strings.Repeat("b", 64)
			case "unknown_field":
				init["apply"] = true
			case "case_alias":
				init["LOCAL_LAB_CONSENT"] = true
			case "null_field":
				init["local_lab_consent"] = nil
			}
			send := func(value any) {
				t.Helper()
				raw, err := json.Marshal(value)
				if err != nil {
					t.Fatal(err)
				}
				if _, err := cw.Write(frame(string(raw))); err != nil {
					t.Fatal(err)
				}
			}
			receive := func(phase string) {
				t.Helper()
				raw, err := readFrame(er, gatewaySessionFrameLimit)
				if err != nil {
					t.Fatal(err)
				}
				var event gatewaySessionEvent
				if err := json.Unmarshal(raw, &event); err != nil {
					t.Fatal(err)
				}
				if event.Phase != phase || event.BeforeSHA != before || event.Session != "session1" {
					t.Fatalf("bad event: %+v", event)
				}
			}
			send(init)
			early := scenario == "consent_missing" || scenario == "consent_false" || scenario == "wrong_session" || scenario == "wrong_sha" || scenario == "wrong_namespace" || scenario == "unknown_field" || scenario == "case_alias" || scenario == "null_field"
			if !early {
				receive("ready")
				command := func(seq int, action string) map[string]any {
					return map[string]any{"schema_version": 1, "kind": "gateway_session_command", "session_id": "session1", "sequence": seq, "action": action, "before_sha256": before}
				}
				if scenario == "cancel" {
					cancel()
				} else if scenario == "eof" {
					cw.Close()
				} else {
					first := command(1, "begin")
					if scenario == "wrong_sequence" {
						first["sequence"] = 2
					}
					send(first)
					if scenario != "journal_failure" && scenario != "namespace_lost" && scenario != "wrong_sequence" {
						receive("apply_requested")
						second := command(2, "applied")
						second["snapshot_path"] = appliedPath
						second["snapshot_sha256"] = applied
						if scenario == "duplicate" {
							second = command(1, "begin")
						}
						if scenario == "applied_wrong_sha" {
							second["snapshot_sha256"] = before
						}
						if scenario == "applied_reused_before" {
							second["snapshot_path"] = path
							second["snapshot_sha256"] = before
						}
						send(second)
						if scenario == "normal" {
							receive("applied")
							send(command(3, "stop"))
							receive("release_requested")
						}
					}
				}
			}
			err = <-done
			if scenario == "normal" {
				if err != nil || strings.Join(journal.events, ",") != "ready,apply_requested,applied,release_requested" {
					t.Fatalf("%v %v", err, journal.events)
				}
			} else {
				if err == nil {
					t.Fatal("invalid session accepted")
				}
				if len(journal.events) > 2 {
					t.Fatal("invalid session advanced", journal.events)
				}
			}
			// A failed durable record must never become an application request.
			if scenario == "journal_failure" {
				if _, err := readFrame(er, gatewaySessionFrameLimit); err == nil {
					t.Fatal("event emitted without journal")
				}
			}
		})
	}
}

func TestSessionSnapshotRejectsSpecialFilesAndTampering(t *testing.T) {
	before, _, path, _ := sessionSnapshots(t)
	link := filepath.Join(t.TempDir(), "link")
	if err := os.Symlink(path, link); err != nil {
		t.Fatal(err)
	}
	for _, p := range []string{link, filepath.Dir(path), "relative.json"} {
		if _, err := readSessionSnapshot(context.Background(), p, before); err == nil {
			t.Fatal("unsafe path accepted")
		}
	}
	if err := os.WriteFile(path, []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := readSessionSnapshot(context.Background(), path, before); err == nil {
		t.Fatal("modified snapshot accepted")
	}
}
