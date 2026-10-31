//go:build linux && !android

package linux

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

type testLabObserver struct {
	failIntent, failResult, mutate bool
	intents, results               int
}

func (o *testLabObserver) ToolIntent(_ LabToolSpec, args []string) error {
	o.intents++
	if len(args) > 1 && args[0] == "qdisc" && args[1] == "add" && o.failIntent {
		return errors.New("intent sync failed")
	}
	if o.mutate {
		args[0] = "unsafe"
	}
	return nil
}

func (o *testLabObserver) ToolResult(call LabToolCall) error {
	o.results++
	if len(call.Arguments) > 1 && call.Arguments[0] == "qdisc" && call.Arguments[1] == "add" && o.failResult {
		return errors.New("result sync failed")
	}
	if o.mutate {
		call.Arguments[0] = "unsafe"
		if len(call.Stdout) > 0 {
			call.Stdout[0] = 'x'
		}
		if call.ExitCode != nil {
			*call.ExitCode = 99
		}
	}
	return nil
}

func TestCakeObserverFailureStopsBeforeDispatchOrBeforeApplied(t *testing.T) {
	for _, before := range []bool{true, false} {
		backend, _, folder := testCakeBackend(t, "normal")
		observer := &testLabObserver{failIntent: before, failResult: !before}
		backend.launch.Observer = observer
		if _, err := backend.Prepare(context.Background()); err != nil {
			t.Fatal(err)
		}
		if _, _, err := backend.Apply(context.Background()); err == nil {
			t.Fatal("recording failure reported success")
		}
		_, err := os.Stat(filepath.Join(folder, "added"))
		if before && !os.IsNotExist(err) {
			t.Fatal("tool dispatched after intent recording failed")
		}
		if !before && err != nil {
			t.Fatal("partial effect not preserved", err)
		}
		count := len(backend.Evidence().Calls)
		if _, _, err := backend.Apply(context.Background()); err == nil || len(backend.Evidence().Calls) != count {
			t.Fatal("failed recorded control retried")
		}
	}
}

func TestCakeObserverCannotMutateArgumentsResultsOrStoredEvidence(t *testing.T) {
	backend, _, _ := testCakeBackend(t, "normal")
	observer := &testLabObserver{mutate: true}
	backend.launch.Observer = observer
	if _, err := backend.Prepare(context.Background()); err != nil {
		t.Fatal(err)
	}
	if _, _, err := backend.Apply(context.Background()); err != nil {
		t.Fatal(err)
	}
	if _, err := backend.Final(context.Background()); err != nil {
		t.Fatal(err)
	}
	if observer.intents != 14 || observer.results != 14 {
		t.Fatal("incomplete observation")
	}
	call := backend.Evidence().Calls[0]
	if call.Arguments[0] != "-V" || call.Stdout[0] != 't' || call.ExitCode == nil || *call.ExitCode != 0 {
		t.Fatal("observer modified retained source")
	}
}
