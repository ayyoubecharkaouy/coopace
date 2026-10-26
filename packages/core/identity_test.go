package core_test

import (
	"crypto/ed25519"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestPublicKeyFingerprintVector(t *testing.T) {
	publicKey := make(ed25519.PublicKey, 32)
	for i := range publicKey {
		publicKey[i] = byte(i)
	}
	id, err := core.DeviceIDForPublicKey(publicKey)
	if err != nil || id != "ed25519:630dcd2966c4336691125448bbb25b4ff412a49c732db2c8abc1b8581bd710dd" {
		t.Fatalf("fingerprint format or algorithm changed: %s, %v", id, err)
	}
	if _, err := core.DeviceIDForPublicKey(publicKey[:31]); err == nil {
		t.Fatal("invalid public key length accepted")
	}
}

func TestGroupConsentIsScopedAndSeparate(t *testing.T) {
	consent := core.GroupConsent{GroupID: "test-group", DeviceID: "device-01"}
	if err := consent.Validate(); err != nil || consent.AllowsObservationSharing("test-group", "device-01") {
		t.Fatal("default consent must grant no sharing")
	}
	consent.Join = true
	if consent.AllowsObservationSharing("test-group", "device-01") {
		t.Fatal("joining implicitly granted observation sharing")
	}
	consent.ShareObservations = true
	if !consent.AllowsObservationSharing("test-group", "device-01") || consent.AllowRelay ||
		consent.AllowsObservationSharing("other-group", "device-01") || consent.AllowsObservationSharing("test-group", "other-device") {
		t.Fatal("consent leaked to another purpose, group or device")
	}
	consent.Join = false
	if consent.Validate() == nil || consent.AllowsObservationSharing("test-group", "device-01") {
		t.Fatal("revoked or inconsistent consent still grants sharing")
	}
	for _, invalid := range []core.GroupConsent{
		{DeviceID: "device-01"}, {GroupID: "bad group", DeviceID: "device-01"},
		{GroupID: "test-group", DeviceID: "bad\nID"}, {GroupID: "test-group", DeviceID: "device-01", AllowRelay: true},
	} {
		if invalid.Validate() == nil {
			t.Errorf("invalid consent accepted: %+v", invalid)
		}
	}
}
