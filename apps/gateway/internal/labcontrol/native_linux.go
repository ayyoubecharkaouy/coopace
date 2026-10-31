//go:build linux && !android

package labcontrol

import (
	"context"
	"errors"
	"time"

	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

// Tools are trusted launcher inputs. There is no CLI/JSON path to this adapter
// yet; the independent supervisor and native entrypoint are separate work.
type nativeTools struct{ ip, tc linux.LabToolSpec }

func runNativeWorker(ctx context.Context, transport *WorkerTransport, session string, started time.Time, tools nativeTools) (linux.CakeLabEvidence, error) {
	identity, err := linux.InspectNetworkNamespaceDescriptor(transport.target)
	if err != nil {
		return linux.CakeLabEvidence{}, errors.Join(err, transport.Close())
	}
	backend, err := linux.NewLabCakeControl(linux.CakeLabLaunch{IP: tools.ip, TC: tools.tc, Namespace: identity, Target: transport.target, Original: transport.original})
	if err != nil {
		return linux.CakeLabEvidence{}, errors.Join(err, transport.Close())
	}
	operations := workerOperations{initial: backend.Prepare, apply: backend.Apply, final: backend.Final}
	err = runWorker(ctx, transport, session, started, operations)
	return backend.Evidence(), err
}
