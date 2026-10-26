//go:build linux && !android

package cli

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestIdentityCommandsKeepKeysPrivateAndStable(t *testing.T) {
	directory := filepath.Join(t.TempDir(), "state")
	var stdout, stderr bytes.Buffer
	if code := runIdentity([]string{"init", "--state-dir", directory}, &stdout, &stderr); code != 0 {
		t.Fatalf("init failed: %s", stderr.String())
	}
	publicOutput := stdout.String()
	if !strings.Contains(publicOutput, "ed25519:") || strings.Contains(publicOutput, "PRIVATE KEY") || !strings.Contains(publicOutput, "hors groupe") {
		t.Fatal("identity output is not public-only and outside-group")
	}
	stdout.Reset()
	if code := runIdentity([]string{"show", "--state-dir", directory}, &stdout, &stderr); code != 0 || stdout.String() != publicOutput {
		t.Fatal("show changed the public identity")
	}
	missing := filepath.Join(t.TempDir(), "missing")
	if code := runIdentity([]string{"show", "--state-dir", missing}, &stdout, &stderr); code != 1 {
		t.Fatal("missing identity did not return an error")
	}
	if _, err := os.Stat(missing); !os.IsNotExist(err) {
		t.Fatal("show created a missing directory")
	}
}

func TestIdentityRequiresExplicitStorage(t *testing.T) {
	for _, args := range [][]string{{"init"}, {"init", "--state-dir", " "}, {"rotate"}, {"show", "extra"}} {
		var stdout, stderr bytes.Buffer
		if code := runIdentity(args, &stdout, &stderr); code != 2 || stdout.Len() != 0 {
			t.Errorf("invalid identity args accepted: %v, code=%d", args, code)
		}
	}
}
