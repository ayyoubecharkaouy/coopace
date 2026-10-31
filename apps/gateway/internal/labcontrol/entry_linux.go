//go:build linux && !android

package labcontrol

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

const workerUsage = "Coopace : processus interne du contrôle CAKE DOWN, réservé au lanceur supervisé.\nDescripteurs hérités requis : contrôle 3, événements 4, cible 5, origine 6, journal 7.\nArguments requis : --session-id, --ip, --ip-sha256, --tc, --tc-sha256.\n"

type workerLaunch struct {
	session string
	tools   nativeTools
}

func parseWorkerLaunch(args []string) (workerLaunch, error) {
	if len(args) != 10 {
		return workerLaunch{}, fmt.Errorf("five internal launch options are required")
	}
	values := map[string]string{}
	for i := 0; i < len(args); i += 2 {
		name, value := args[i], args[i+1]
		if len(name) > 32 || len(value) > 4096 || value == "" {
			return workerLaunch{}, fmt.Errorf("invalid internal launch option")
		}
		switch name {
		case "--session-id", "--ip", "--ip-sha256", "--tc", "--tc-sha256":
		default:
			return workerLaunch{}, fmt.Errorf("unknown internal launch option")
		}
		if _, exists := values[name]; exists {
			return workerLaunch{}, fmt.Errorf("duplicate internal launch option")
		}
		values[name] = value
	}
	if !validSession(values["--session-id"]) {
		return workerLaunch{}, fmt.Errorf("invalid trusted session ID")
	}
	tools := nativeTools{ip: linux.LabToolSpec{Path: values["--ip"], SHA256: values["--ip-sha256"]}, tc: linux.LabToolSpec{Path: values["--tc"], SHA256: values["--tc-sha256"]}}
	for _, spec := range []linux.LabToolSpec{tools.ip, tools.tc} {
		if err := spec.Validate(); err != nil {
			return workerLaunch{}, err
		}
	}
	return workerLaunch{values["--session-id"], tools}, nil
}

type workerContractError struct{ error }

func contractFailure(err error) error       { return workerContractError{err} }
func (e workerContractError) Unwrap() error { return e.error }

type workerSignalError struct{ signal syscall.Signal }

func (e workerSignalError) Error() string {
	return fmt.Sprintf("worker interrupted by signal %d", e.signal)
}

func watchWorkerSignals(parent context.Context) (context.Context, func()) {
	ctx, cancel := context.WithCancelCause(parent)
	ch := make(chan os.Signal, 1)
	signal.Notify(ch, syscall.SIGHUP, syscall.SIGINT, syscall.SIGTERM)
	done := make(chan struct{})
	go func() {
		defer close(done)
		select {
		case value := <-ch:
			cancel(workerSignalError{value.(syscall.Signal)})
		case <-ctx.Done():
		}
	}()
	return ctx, func() { signal.Stop(ch); cancel(nil); <-done }
}

type recordedWorker func(context.Context, *WorkerTransport, string, time.Time, nativeTools, *workerJournal) (linux.CakeLabEvidence, error)

// RunInternalWorker is only for the dedicated binary. The launcher must create
// and sync the exclusive journal and own all inherited slots before exec.
// This entrypoint never creates resources or enters a network namespace.
func RunInternalWorker(ctx context.Context, args []string, version string, started time.Time, stderr io.Writer) int {
	return runInternalWorker(ctx, args, version, started, stderr, runRecordedNativeWorker)
}

func runInternalWorker(parent context.Context, args []string, version string, started time.Time, stderr io.Writer, execute recordedWorker) int {
	if len(args) == 1 && args[0] == "--help" {
		if _, err := io.WriteString(stderr, workerUsage); err != nil {
			return 1
		}
		return 0
	}
	diagnostic := func(err error) {
		text := err.Error()
		if len(text) > 4096 {
			text = text[:4096]
		}
		fmt.Fprintln(stderr, text)
	}
	launch, err := parseWorkerLaunch(args)
	if err != nil {
		diagnostic(err)
		return 2
	}
	journal, err := openInheritedJournal(launch.session, started)
	if err != nil {
		diagnostic(err)
		return 2
	}
	transport, bootstrapErr := OpenInheritedTransport()
	ctx, stop := watchWorkerSignals(parent)
	defer stop()
	var target, original *journalNamespace
	if transport != nil {
		for i, file := range []*os.File{transport.target, transport.original} {
			identity, err := linux.InspectNetworkNamespaceDescriptor(file)
			if err != nil {
				bootstrapErr = errors.Join(bootstrapErr, err)
				continue
			}
			observed := &journalNamespace{identity.Device, identity.Inode}
			if i == 0 {
				target = observed
			} else {
				original = observed
			}
		}
	}
	// The header precedes all external tools, including failure at bootstrap.
	err = journal.Record("launch", struct {
		Version      string               `json:"coopace_version"`
		Build        journalBuildInfo     `json:"build"`
		PID          int                  `json:"pid"`
		OS           string               `json:"os"`
		Architecture string               `json:"architecture"`
		Purpose      string               `json:"purpose"`
		Reference    core.CakeReferenceID `json:"reference"`
		IP           journalToolSpec      `json:"ip_tool"`
		TC           journalToolSpec      `json:"tc_tool"`
		Target       *journalNamespace    `json:"target_namespace"`
		Original     *journalNamespace    `json:"original_namespace"`
	}{version, journalBuild(), os.Getpid(), runtime.GOOS, runtime.GOARCH, "cake_down_control", core.CakeReferenceIPv4LabV1, journalToolSpec{launch.tools.ip.Path, launch.tools.ip.SHA256}, journalToolSpec{launch.tools.tc.Path, launch.tools.tc.SHA256}, target, original})
	var evidence linux.CakeLabEvidence
	if err == nil && bootstrapErr == nil {
		evidence, err = execute(ctx, transport, launch.session, started, launch.tools, journal)
	} else if transport != nil {
		err = errors.Join(err, transport.Close())
	}
	err = errors.Join(err, bootstrapErr)
	code := 0
	if err != nil {
		code = 1
	}
	var contract workerContractError
	if bootstrapErr != nil || errors.As(err, &contract) {
		code = 2
	}
	if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, os.ErrDeadlineExceeded) {
		code = 1
	}
	var interrupted workerSignalError
	if errors.As(context.Cause(ctx), &interrupted) {
		code = 128 + int(interrupted.signal)
		err = errors.Join(context.Cause(ctx), err)
	} else if errors.Is(parent.Err(), context.Canceled) {
		code = 130
		err = errors.Join(parent.Err(), err)
	}
	message := ""
	if err != nil {
		message = err.Error()
	}
	journalErr := journal.Record("worker_exit", struct {
		Code         int    `json:"intended_exit_code"`
		State        string `json:"backend_state"`
		AddAttempted bool   `json:"add_attempted"`
		Error        string `json:"error"`
		Cleanup      string `json:"cleanup"`
		Traffic      bool   `json:"traffic_generated"`
		Active       bool   `json:"active_path_verified"`
	}{code, evidence.State, evidence.AddAttempted, message, "not_attested", false, false})
	journalErr = errors.Join(journalErr, journal.Close())
	if journalErr != nil {
		err = errors.Join(err, journalErr)
		code = 1
	}
	if err != nil {
		diagnostic(err)
	}
	return code
}
