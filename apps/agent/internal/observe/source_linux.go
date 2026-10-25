//go:build linux && !android

package observe

import (
	"github.com/ayyoubecharkaouy/coopace/packages/core"
	linuxplatform "github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

const sourceName = "Linux /proc/net/dev"

func readCounters() ([]core.InterfaceCounters, error) {
	return linuxplatform.ReadTrafficCounters()
}
