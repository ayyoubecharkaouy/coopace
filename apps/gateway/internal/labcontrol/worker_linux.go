//go:build linux && !android

package labcontrol

import (
	"context"
	"errors"
	"fmt"
	"os"
	"time"

	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

// This private driver accepts the native adapter wired in native_linux.go or
// process-backed test fakes. The internal entry supplies durable recording;
// interface/DOWN checks and bounded tool calls belong to the native adapter.
type workerOperations struct {
	initial func(context.Context) ([]byte, error)
	apply   func(context.Context) ([]byte, linux.CakeProducerProfile, error)
	final   func(context.Context) ([]byte, error)
	// Private injection for protocol tests only; nil selects the native verifier.
	verify func(linux.NetworkNamespaceIdentity, *os.File, *os.File) error
	// Production entrypoints require this synchronous durable recorder.
	record func(string, any) error
}

func runWorker(ctx context.Context, transport *WorkerTransport, expectedSession string, started time.Time, operations workerOperations) (result error) {
	defer func() { result = errors.Join(result, transport.Close()) }()
	if !validSession(expectedSession) || started.IsZero() || started.After(time.Now()) {
		return fmt.Errorf("invalid trusted worker launch")
	}
	if operations.initial == nil || operations.apply == nil || operations.final == nil {
		return fmt.Errorf("worker tool backend is incomplete")
	}
	ctx, cancel := context.WithDeadline(ctx, started.Add(WorkerLifetime))
	defer cancel()
	request, err := transport.ReadRequest(ctx, started.Add(BoundaryTimeout))
	if err != nil {
		return contractFailure(err)
	}
	session, err := NewSession(request, expectedSession, started)
	if err != nil {
		return contractFailure(err)
	}
	if operations.verify != nil {
		session.verify = operations.verify
	}
	if err := session.BindNamespace(transport.target, transport.original); err != nil {
		return contractFailure(err)
	}
	record := func(event string, data any) error {
		if operations.record == nil {
			return nil
		}
		if err := operations.record(event, data); err != nil {
			return session.Abort(err)
		}
		return session.Check()
	}
	if err := record("context_accepted", struct {
		Reference string `json:"reference"`
	}{string(request.reference)}); err != nil {
		return err
	}
	step, cancelStep := context.WithDeadline(ctx, session.boundary)
	initial, err := operations.initial(step)
	cancelStep()
	if err != nil {
		return session.Abort(err)
	}
	if err := session.Ready(initial); err != nil {
		return err
	}
	ready, err := eventFrame(request.session, "ready", nil)
	if err != nil {
		return session.Abort(err)
	}
	if err := record("ready", nil); err != nil {
		return err
	}
	if err := transport.send(ctx, session, ready); err != nil {
		return err
	}
	if err := transport.receive(ctx, session); err != nil {
		return contractFailure(err)
	}
	if err := record("apply_received", nil); err != nil {
		return err
	}
	step, cancelStep = context.WithDeadline(ctx, session.boundary)
	raw, profile, err := operations.apply(step)
	cancelStep()
	if err != nil {
		return session.Abort(err)
	}
	reading, err := session.Applied(raw, profile)
	if err != nil {
		return err
	}
	applied, err := eventFrame(request.session, "applied", &reading)
	if err != nil {
		return session.Abort(err)
	}
	if err := record("applied", struct {
		Producer linux.CakeProducerProfile `json:"producer_profile"`
	}{profile}); err != nil {
		return err
	}
	if err := transport.send(ctx, session, applied); err != nil {
		return err
	}
	// Keep the finish boundary: receiving finish does not grant another five
	// seconds for the final observation or extend the worker's lifetime.
	finishDeadline := session.boundary
	if err := transport.receive(ctx, session); err != nil {
		return contractFailure(err)
	}
	if err := record("finish_received", nil); err != nil {
		return err
	}
	if err := session.verifyBinding(); err != nil {
		return err
	}
	step, cancelStep = context.WithDeadline(ctx, finishDeadline)
	defer cancelStep()
	final, err := operations.final(step)
	if err != nil {
		return session.Abort(err)
	}
	if _, err := linux.ParseCakeReading(final, profile); err != nil {
		return session.Abort(err)
	}
	if err := session.verifyBinding(); err != nil {
		return err
	}
	if err := step.Err(); err != nil {
		return session.Abort(err)
	}
	if !time.Now().Before(finishDeadline) {
		return session.Abort(os.ErrDeadlineExceeded)
	}
	if err := record("final_verified", nil); err != nil {
		return err
	}
	if !time.Now().Before(finishDeadline) {
		return session.Abort(os.ErrDeadlineExceeded)
	}
	if err := step.Err(); err != nil {
		return session.Abort(err)
	}
	return nil
}
