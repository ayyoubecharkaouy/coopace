//go:build linux && !android

package cli

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/group"
	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/identity"
)

func TestGroupCLIRequiresConsentAndReportsOnlyLocalConfiguration(t *testing.T) {
	aDir, bDir := filepath.Join(t.TempDir(), "a"), filepath.Join(t.TempDir(), "b")
	if _, err := identity.Init(aDir); err != nil {
		t.Fatal(err)
	}
	b, err := identity.Init(bDir)
	if err != nil {
		t.Fatal(err)
	}
	public, _ := b.Public()
	var stdout, stderr bytes.Buffer
	if code := Run([]string{"identity", "export-cert", "--state-dir", aDir}, "dev", &stdout, &stderr); code != 0 {
		t.Fatalf("export failed: %s", &stderr)
	}
	a, _ := identity.Load(aDir)
	aPublic, _ := a.Public()
	if _, err := identity.ParseCertificate(stdout.Bytes(), aPublic.DeviceID); err != nil {
		t.Fatalf("export contains extra output or wrong identity: %v", err)
	}
	bPEM, err := identity.ExportCertificate(bDir)
	if err != nil {
		t.Fatal(err)
	}
	peerFile := filepath.Join(t.TempDir(), "peer.crt")
	if err := os.WriteFile(peerFile, bPEM, 0600); err != nil {
		t.Fatal(err)
	}
	args := []string{"group", "configure", "--state-dir", aDir, "--group-id", "local-test", "--peer-cert", peerFile, "--peer-id", string(public.DeviceID)}
	stdout.Reset()
	if code := Run(args, "dev", &stdout, &stderr); code != 2 {
		t.Fatalf("missing --join accepted: %d", code)
	}
	if code := Run(append(args, "--join"), "dev", &stdout, &stderr); code != 0 {
		t.Fatalf("configure failed: %s", &stderr)
	}
	profile, err := group.LoadProfile(aDir)
	if err != nil || !profile.Consent.Join || profile.Consent.ShareObservations {
		t.Fatalf("unexpected persisted consent: %v", err)
	}
	stdout.Reset()
	if code := Run([]string{"group", "show", "--state-dir", aDir}, "dev", &stdout, &stderr); code != 0 || !strings.Contains(stdout.String(), "configuration locale, déconnecté") || strings.Contains(stdout.String(), "PRIVATE KEY") {
		t.Fatalf("invalid state output: %d %s", code, &stdout)
	}
	if code := Run([]string{"group", "revoke", "--state-dir", aDir}, "dev", &stdout, &stderr); code != 0 {
		t.Fatalf("revoke failed: %s", &stderr)
	}
	profile, err = group.LoadProfile(aDir)
	if err != nil || profile.Consent.Join {
		t.Fatal("CLI revocation was not persisted")
	}
}

func TestGroupCLIRejectsInvalidArgumentsBeforeIO(t *testing.T) {
	for _, args := range [][]string{
		{"group", "unknown"}, {"group", "show"}, {"group", "configure", "--state-dir", "unused", "--join"},
		{"group", "exchange", "--state-dir", "unused"}, {"group", "exchange", "--state-dir", "unused", "--target", "example.com:443"},
		{"group", "listen", "--state-dir", "unused", "--listen", "224.0.0.1:8766"}, {"group", "show", "--state-dir", "unused", "extra"},
	} {
		var stdout, stderr bytes.Buffer
		if code := Run(args, "dev", &stdout, &stderr); code != 2 || stdout.Len() != 0 {
			t.Errorf("invalid arguments accepted: %v code=%d", args, code)
		}
	}
}
