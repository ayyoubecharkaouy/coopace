// Package diagnostic assembles a local, read-only gateway inventory.
package diagnostic

import (
	"context"
	"runtime"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/buildinfo"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

// Report is a local observation, not a backup or permission to manage traffic.
type Report struct {
	Version      string
	OS           string
	Architecture string
	CollectedAt  time.Time
	Inventory    core.GatewayInventory
	Build        buildinfo.Info
}

func Local(ctx context.Context, version string) (Report, error) {
	ctx, cancel := context.WithTimeout(ctx, 8*time.Second)
	defer cancel()
	inventory, err := collectNative(ctx)
	if err != nil {
		return Report{}, err
	}
	return Report{Version: version, OS: runtime.GOOS, Architecture: runtime.GOARCH, CollectedAt: time.Now().UTC(), Inventory: inventory, Build: buildinfo.Local()}, nil
}
