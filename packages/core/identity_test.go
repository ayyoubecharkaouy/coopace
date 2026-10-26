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
