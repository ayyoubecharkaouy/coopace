package diagnostic

import (
	"runtime/debug"
	"testing"
)

func TestBuildMetadataDistinguishesMissingCleanAndModified(t *testing.T) {
	missing := buildFromSettings("go-test", nil)
	if missing.GoVersion != "go-test" || missing.Revision != "" || missing.Modified != nil {
		t.Fatal("missing build metadata became a clean revision")
	}
	for _, value := range []string{"false", "true"} {
		info := buildFromSettings("go-test", []debug.BuildSetting{{Key: "vcs", Value: "git"}, {Key: "vcs.revision", Value: "abc123"}, {Key: "vcs.modified", Value: value}, {Key: "-ldflags", Value: "not-for-the-report"}})
		if info.VCS != "git" || info.Revision != "abc123" || info.Modified == nil || *info.Modified != (value == "true") {
			t.Fatalf("build provenance lost: %+v", info)
		}
	}
	invalid := buildFromSettings("go-test", []debug.BuildSetting{{Key: "vcs.modified", Value: "unknown"}})
	if invalid.Modified != nil {
		t.Fatal("invalid metadata became a clean build")
	}
}
