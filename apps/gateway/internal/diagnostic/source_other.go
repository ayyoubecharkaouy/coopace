//go:build !linux || android

package diagnostic

import (
	"context"
	"fmt"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func collectNative(context.Context) (core.GatewayInventory, error) {
	return core.GatewayInventory{}, fmt.Errorf("diagnostic de passerelle disponible uniquement sous Linux à cette étape ; l'adaptation de ce système reste à développer")
}
