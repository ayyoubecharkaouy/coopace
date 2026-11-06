//go:build !linux || android

package linux

import (
	"context"
	"fmt"
)

func SnapshotGatewayQueues(ctx context.Context, name string) (GatewayQueueSnapshot, error) {
	if err := ctx.Err(); err != nil {
		return GatewayQueueSnapshot{}, err
	}
	return GatewayQueueSnapshot{}, fmt.Errorf("capture des files disponible uniquement sous Linux à cette étape")
}
