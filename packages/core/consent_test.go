package core_test

import (
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

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
