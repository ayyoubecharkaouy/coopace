package status

import (
	"runtime"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestDesktopPlatforms(t *testing.T) {
	for _, platform := range []struct {
		name string
		want core.OperatingSystem
	}{
		{"linux", core.OSLinux},
		{"windows", core.OSWindows},
	} {
		t.Run(platform.name, func(t *testing.T) {
			report, err := forPlatform("test-version", platform.name, "arm64")
			if err != nil {
				t.Fatal(err)
			}
			if report.Version != "test-version" || report.OS != platform.want || report.Architecture != "arm64" || report.Role != core.RoleAgent {
				t.Fatalf("unexpected local report: %+v", report)
			}
		})
	}
}

func TestUnsupportedDesktopPlatform(t *testing.T) {
	for _, platform := range []string{"android", "darwin", "", "unknown"} {
		t.Run(platform, func(t *testing.T) {
			if _, err := forPlatform("dev", platform, "amd64"); err == nil {
				t.Fatal("unsupported desktop platform accepted")
			}
		})
	}
}

func TestLocalReportsCurrentExecutablePlatform(t *testing.T) {
	report, err := Local("dev")
	if runtime.GOOS != "linux" && runtime.GOOS != "windows" {
		if err == nil {
			t.Fatal("unsupported platform accepted")
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	if string(report.OS) != runtime.GOOS || report.Architecture != runtime.GOARCH {
		t.Fatalf("report does not match the running executable: %+v", report)
	}
}
