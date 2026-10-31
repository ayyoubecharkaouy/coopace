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

// This private driver is exercised with process-backed fake tools. It has no
// native tool backend or CLI yet. The future backend must inspect interfaces and
// DOWN state, enforce tool/output limits, and collect all dumps itself.
type workerOperations struct {
	initial func(context.Context) ([]byte, error)
	apply   func(context.Context) ([]byte, linux.CakeProducerProfile, error)
	final   func(context.Context) ([]byte, error)
	// Private injection for protocol tests only; nil selects the native verifier.
	verify func(linux.NetworkNamespaceIdentity, *os.File, *os.File) error
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
		return err
	}
	session, err := NewSession(request, expectedSession, started)
	if err != nil {
		return err
	}
	if operations.verify != nil {
		session.verify = operations.verify
	}
	if err := session.BindNamespace(transport.target, transport.original); err != nil {
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
	if err := transport.send(ctx, session, ready); err != nil {
		return err
	}
	if err := transport.receive(ctx, session); err != nil {
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
	if err := transport.send(ctx, session, applied); err != nil {
		return err
	}
	// Keep the finish boundary: receiving finish does not grant another five
	// seconds for the final observation or extend the worker's lifetime.
	finishDeadline := session.boundary
	if err := transport.receive(ctx, session); err != nil {
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
	return nil
}
