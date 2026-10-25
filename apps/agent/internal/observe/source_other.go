//go:build !linux || android

package observe

import (
	"fmt"
	"runtime"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const sourceName = "indisponible"

func readCounters() ([]core.InterfaceCounters, error) {
	return nil, fmt.Errorf("observation du trafic non disponible sur %s dans cette version", runtime.GOOS)
}
