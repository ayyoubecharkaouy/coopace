// Package status describes the local desktop agent without changing the system.
package status

import (
	"fmt"
	"runtime"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

// Report is a local application snapshot, not a protocol message or group identity.
type Report struct {
	Version      string
	OS           core.OperatingSystem
	Architecture string
	Role         core.Role
}

// Local reports the platform of this executable. No network probing, persistent
// identity, group membership or daemon discovery is performed at this stage.
func Local(version string) (Report, error) {
	return forPlatform(version, runtime.GOOS, runtime.GOARCH)
}

func forPlatform(version, operatingSystem, architecture string) (Report, error) {
	var platform core.OperatingSystem
	switch operatingSystem {
	case "linux":
		platform = core.OSLinux
	case "windows":
		platform = core.OSWindows
	default:
		return Report{}, fmt.Errorf("système non pris en charge par l'agent de bureau : %q", operatingSystem)
	}
	return Report{
		Version:      version,
		OS:           platform,
		Architecture: architecture,
		Role:         core.RoleAgent,
	}, nil
}
