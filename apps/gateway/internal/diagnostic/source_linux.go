//go:build linux && !android

package diagnostic

import (
	"context"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
	linuxplatform "github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

func collectNative(ctx context.Context) (core.GatewayInventory, error) {
	return linuxplatform.InspectGateway(ctx)
}
