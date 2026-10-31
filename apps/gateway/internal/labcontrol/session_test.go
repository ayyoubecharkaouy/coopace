package labcontrol

import (
	"bytes"
	"errors"
	"io"
	"os"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

func testSession(t *testing.T) (*Session, *time.Time, *int) {
	t.Helper()
	now := time.Date(2026, 10, 31, 12, 0, 0, 0, time.UTC)
	request, err := ReadRequest(bytes.NewReader(frame(requestJSON)))
	if err != nil {
		t.Fatal(err)
	}
	s, err := newSession(request, "abcd1234", now, func() time.Time { return now })
	if err != nil {
		t.Fatal(err)
	}
	checks := new(int)
	// Protocol tests simulate the separate, read-only namespace verifier. No
	// successful binding to a newly created namespace is claimed by these tests.
	s.verify = func(identity linux.NetworkNamespaceIdentity, _, _ *os.File) error {
		*checks += 1
		if identity != request.NamespaceIdentity() {
			t.Fatal("namespace context changed")
		}
		return nil
	}
	return s, &now, checks
}

func readySession(t *testing.T) (*Session, *time.Time, *int) {
	t.Helper()
	s, now, checks := testSession(t)
	if err := s.BindNamespace(nil, nil); err != nil {
		t.Fatal(err)
	}
	if err := s.Ready([]byte("[]")); err != nil {
		t.Fatal(err)
	}
	return s, now, checks
}

func control(t *testing.T, action, session string) Command {
	t.Helper()
	value, err := ReadCommand(bytes.NewReader(frame(commandJSON(action, session))))
	if err != nil {
		t.Fatal(err)
	}
	return value
}

func appliedFixture(t *testing.T) []byte {
	t.Helper()
	data, err := os.ReadFile("../../../../platforms/linux/testdata/cake/down.json")
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestSessionOneShotSequenceRequiresBindingReadinessAndConformantReading(t *testing.T) {
	s, _, checks := readySession(t)
	if s.Phase() != WaitingApply {
		t.Fatal("apply admitted before readiness")
	}
	if err := s.Receive(bytes.NewReader(frame(commandJSON("apply", "abcd1234")))); err != nil {
		t.Fatal(err)
	}
	if s.Phase() != Applying {
		t.Fatal("apply not tracked")
	}
	reading, err := s.Applied(appliedFixture(t), linux.CakeIPRoute2V610)
	if err != nil || len(reading.Raw) == 0 || s.Phase() != WaitingFinish {
		t.Fatalf("conformant reading not accepted: %v", err)
	}
	if err := s.Accept(control(t, "finish", "abcd1234")); err != nil || s.Phase() != Finished {
		t.Fatalf("finish failed: %v", err)
	}
	if *checks != 5 {
		t.Fatalf("binding not rechecked on each boundary: %d", *checks)
	}
	if err := s.Accept(control(t, "apply", "abcd1234")); err == nil || s.Phase() != Failed {
		t.Fatal("finished session replayed")
	}
}

func TestSessionRejectsWrongTrustedSessionZeroValuesAndInvalidStart(t *testing.T) {
	request, err := ReadRequest(bytes.NewReader(frame(requestJSON)))
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	for _, id := range []string{"", "other123", "ABCD1234"} {
		if _, err := NewSession(request, id, now); err == nil {
			t.Fatal("unbound session ID accepted")
		}
	}
	if _, err := NewSession(Request{}, "abcd1234", now); err == nil {
		t.Fatal("zero request accepted")
	}
	for _, started := range []time.Time{{}, now.Add(time.Hour), now.Add(-WorkerLifetime)} {
		if _, err := NewSession(request, "abcd1234", started); err == nil {
			t.Fatal("invalid or expired start accepted")
		}
	}
	var zero Session
	if err := zero.Check(); err == nil || zero.Phase() != Failed {
		t.Fatal("zero session not rejected")
	}
}

func TestSessionProtocolFailuresArePermanent(t *testing.T) {
	for _, scenario := range []string{"early_apply", "early_ready", "finish_before_apply", "duplicate_apply", "bad_reading", "wrong_session", "zero_command", "eof", "malformed"} {
		t.Run(scenario, func(t *testing.T) {
			s, _, _ := testSession(t)
			var err error
			if scenario == "early_apply" {
				err = s.Accept(control(t, "apply", "abcd1234"))
			} else if scenario == "early_ready" {
				err = s.Ready([]byte("[]"))
			} else {
				if e := s.BindNamespace(nil, nil); e != nil {
					t.Fatal(e)
				}
				if e := s.Ready([]byte("[]")); e != nil {
					t.Fatal(e)
				}
				switch scenario {
				case "finish_before_apply":
					err = s.Accept(control(t, "finish", "abcd1234"))
				case "duplicate_apply":
					if e := s.Accept(control(t, "apply", "abcd1234")); e != nil {
						t.Fatal(e)
					}
					err = s.Accept(control(t, "apply", "abcd1234"))
				case "bad_reading":
					if e := s.Accept(control(t, "apply", "abcd1234")); e != nil {
						t.Fatal(e)
					}
					_, err = s.Applied([]byte("[]"), linux.CakeIPRoute2V610)
				case "wrong_session":
					err = s.Accept(control(t, "apply", "other123"))
				case "zero_command":
					err = s.Accept(Command{})
				case "eof":
					err = s.Receive(bytes.NewReader(nil))
					if !errors.Is(err, io.EOF) {
						t.Fatal(err)
					}
				case "malformed":
					err = s.Receive(bytes.NewReader(frame(`{"action":"apply"}`)))
				}
			}
			if err == nil || s.Phase() != Failed {
				t.Fatalf("protocol violation accepted: %v", err)
			}
			if err := s.Accept(control(t, "apply", "abcd1234")); err == nil {
				t.Fatal("failed session retried")
			}
		})
	}
}

func TestSessionRechecksChangedBindingAndRejectsUnconfiguredQueueSubstitution(t *testing.T) {
	s, _, _ := readySession(t)
	lost := errors.New("namespace no longer matches")
	s.verify = func(linux.NetworkNamespaceIdentity, *os.File, *os.File) error { return lost }
	if err := s.Accept(control(t, "apply", "abcd1234")); !errors.Is(err, lost) || s.Phase() != Failed {
		t.Fatal("changed binding ignored")
	}
	s, _, _ = testSession(t)
	s.BindNamespace(nil, nil)
	if err := s.Ready(appliedFixture(t)); err == nil || s.Phase() != Failed {
		t.Fatal("existing CAKE admitted as fresh empty root")
	}
}

func TestSessionDeadlinesAreInclusiveAndNeverExtendedByChecks(t *testing.T) {
	s, now, _ := readySession(t)
	absolute := s.deadline
	boundary := s.boundary
	for i := 0; i < 4; i++ {
		*now = now.Add(time.Second)
		if err := s.Check(); err != nil {
			t.Fatal(err)
		}
	}
	if s.boundary != boundary || s.deadline != absolute {
		t.Fatal("checks extended deadlines")
	}
	*now = boundary
	if err := s.Accept(control(t, "apply", "abcd1234")); err == nil || s.Phase() != Failed {
		t.Fatal("exact boundary expiry accepted")
	}
	s, now, _ = readySession(t)
	*now = s.deadline
	if err := s.Check(); err == nil || s.Phase() != Failed {
		t.Fatal("worker lifetime ignored")
	}
	s, now, _ = readySession(t)
	*now = now.Add(4 * time.Second)
	if err := s.Accept(control(t, "apply", "abcd1234")); err != nil {
		t.Fatal(err)
	}
	if s.deadline != absolute {
		t.Fatal("apply extended overall lifetime")
	}
}

func TestSessionProductionVerifierCannotBeReplacedByDeclaredIdentity(t *testing.T) {
	request, err := ReadRequest(bytes.NewReader(frame(requestJSON)))
	if err != nil {
		t.Fatal(err)
	}
	s, err := NewSession(request, "abcd1234", time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if err := s.BindNamespace(nil, nil); err == nil || s.Phase() != Failed {
		t.Fatal("declared namespace numbers admitted absent descriptors")
	}
}
