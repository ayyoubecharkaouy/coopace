//go:build linux && !android

package labcontrol

import (
	"context"
	"errors"
	"time"

	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

// Tools are trusted launcher inputs, supplied by the dedicated internal entry.
// No plan/scenario can configure this adapter; supervisor integration is separate.
type nativeTools struct{ ip, tc linux.LabToolSpec }

func runNativeWorker(ctx context.Context, transport *WorkerTransport, session string, started time.Time, tools nativeTools) (linux.CakeLabEvidence, error) {
	return runRecordedNativeWorker(ctx, transport, session, started, tools, nil)
}

func runRecordedNativeWorker(ctx context.Context, transport *WorkerTransport, session string, started time.Time, tools nativeTools, journal *workerJournal) (linux.CakeLabEvidence, error) {
	identity, err := linux.InspectNetworkNamespaceDescriptor(transport.target)
	if err != nil {
		return linux.CakeLabEvidence{}, errors.Join(err, transport.Close())
	}
	launch := linux.CakeLabLaunch{IP: tools.ip, TC: tools.tc, Namespace: identity, Target: transport.target, Original: transport.original}
	if journal != nil {
		launch.Observer = journal
	}
	backend, err := linux.NewLabCakeControl(launch)
	if err != nil {
		return linux.CakeLabEvidence{}, errors.Join(err, transport.Close())
	}
	operations := workerOperations{initial: backend.Prepare, apply: backend.Apply, final: backend.Final}
	if journal != nil {
		operations.record = journal.Record
	}
	err = runWorker(ctx, transport, session, started, operations)
	return backend.Evidence(), err
}
