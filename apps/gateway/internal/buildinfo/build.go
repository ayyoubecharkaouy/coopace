// Package buildinfo reads executable provenance without collecting an inventory.
package buildinfo

import (
	"runtime"
	"runtime/debug"
	"strconv"
)

// Info describes the executable at compilation time, not the current checkout.
// Missing VCS data is distinct from a known, clean working tree.
type Info struct {
	GoVersion string
	VCS       string
	Revision  string
	Modified  *bool
}

func Local() Info {
	info, ok := debug.ReadBuildInfo()
	if !ok {
		return Info{GoVersion: runtime.Version()}
	}
	return buildFromSettings(info.GoVersion, info.Settings)
}

func buildFromSettings(goVersion string, settings []debug.BuildSetting) Info {
	result := Info{GoVersion: goVersion}
	for _, setting := range settings {
		switch setting.Key {
		case "vcs":
			result.VCS = setting.Value
		case "vcs.revision":
			result.Revision = setting.Value
		case "vcs.modified":
			if value, err := strconv.ParseBool(setting.Value); err == nil {
				result.Modified = &value
			}
		}
	}
	return result
}
