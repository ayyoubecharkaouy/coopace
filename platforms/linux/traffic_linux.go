//go:build linux && !android

package linux

import (
	"fmt"
	"os"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

// ReadTrafficCounters reads aggregate interface counters in this network namespace.
func ReadTrafficCounters() ([]core.InterfaceCounters, error) {
	file, err := os.Open("/proc/net/dev")
	if err != nil {
		return nil, fmt.Errorf("opening /proc/net/dev: %w", err)
	}
	defer file.Close()
	return parseTrafficCounters(file)
}
