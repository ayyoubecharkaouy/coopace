//go:build linux && !android

package group

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestProfileRejectsTamperingSymlinksAndOversizedFiles(t *testing.T) {
	for _, change := range []string{"identity", "relay", "size", "symlink", "unknown"} {
		t.Run(change, func(t *testing.T) {
			a, _, directory, _ := testPair(t, false, false)
			path := filepath.Join(directory, profileFile)
			switch change {
			case "identity", "relay":
				profile := a.profile
				if change == "identity" {
					profile.Consent.DeviceID = profile.PeerID
				} else {
					profile.Consent.AllowRelay = true
				}
				data, _ := json.Marshal(profile)
				if err := os.WriteFile(path, data, 0600); err != nil {
					t.Fatal(err)
				}
			case "size":
				if err := os.WriteFile(path, []byte(strings.Repeat(" ", maxProfileBytes+1)), 0600); err != nil {
					t.Fatal(err)
				}
			case "unknown":
				data, _ := os.ReadFile(path)
				data = append([]byte(`{"unknown":true,`), data[1:]...)
				if err := os.WriteFile(path, data, 0600); err != nil {
					t.Fatal(err)
				}
			case "symlink":
				backup := filepath.Join(directory, "copy.json")
				if err := os.Rename(path, backup); err != nil {
					t.Fatal(err)
				}
				if err := os.Symlink(backup, path); err != nil {
					t.Fatal(err)
				}
			}
			if _, err := LoadProfile(directory); err == nil {
				t.Fatal("unsafe profile loaded")
			}
			if err := a.check(); err == nil {
				t.Fatal("changed/unsafe profile did not invalidate active approval")
			}
		})
	}
}

func TestProfileRequiresApprovalAndProtectsLocalConsent(t *testing.T) {
	a, _, aDir, _ := testPair(t, false, false)
	options := Configuration{GroupID: "test-group", PeerID: a.profile.PeerID, PeerCertificate: []byte(a.profile.PeerCertificate)}
	if _, err := Configure(aDir, options); err == nil {
		t.Fatal("implicit joining accepted")
	}
	options.Join = true
	options.PeerID = a.profile.Consent.DeviceID
	if _, err := Configure(aDir, options); err == nil {
		t.Fatal("self approval accepted")
	}
	options.PeerID = core.DeviceID("ed25519:" + strings.Repeat("a", 64))
	if _, err := Configure(aDir, options); err == nil {
		t.Fatal("wrong fingerprint accepted")
	}
	profile, err := LoadProfile(aDir)
	if err != nil || profile.Consent.ShareObservations {
		t.Fatalf("sharing was enabled by default: %v", err)
	}
	if err := Revoke(aDir); err != nil {
		t.Fatal(err)
	}
	if _, err := loadEndpoint(aDir); err == nil {
		t.Fatal("revoked profile started an exchange")
	}
	if err := Revoke(aDir); err != nil {
		t.Fatal("revoke should be idempotent")
	}
	profile, err = LoadProfile(aDir)
	if err != nil || profile.Consent.Join || profile.Consent.ShareObservations {
		t.Fatalf("revocation not persisted: %v", err)
	}
	if err := os.Chmod(filepath.Join(aDir, profileFile), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadProfile(aDir); err == nil {
		t.Fatal("nonprivate profile loaded")
	}
}
