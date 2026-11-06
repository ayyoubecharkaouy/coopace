//go:build linux && !android

package linux

import (
	"context"
	"net"
	"os/exec"
	"path/filepath"
	"time"
)

// SnapshotGatewayQueues observes an explicitly selected interface without
// changing its state. Existing bounded diagnostic queries are reused.
func SnapshotGatewayQueues(ctx context.Context, name string) (GatewayQueueSnapshot, error) {
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	return collectGatewayQueueSnapshot(ctx, name, gatewaySnapshotSources{
		interfaceByName: net.InterfaceByName,
		lookPath: func(name string) (string, error) {
			path, err := exec.LookPath(name)
			if err != nil {
				return "", err
			}
			path, err = filepath.Abs(path)
			if err != nil {
				return "", err
			}
			return filepath.EvalSymlinks(path)
		},
		run: runGatewayQuery,
	})
}
