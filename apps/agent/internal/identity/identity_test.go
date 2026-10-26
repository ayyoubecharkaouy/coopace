package identity

import (
	"crypto/ed25519"
	"encoding/base64"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestPublicIdentityMatchesItsKey(t *testing.T) {
	local, err := generate()
	if err != nil {
		t.Fatal(err)
	}
	public, err := local.Public()
	if err != nil {
		t.Fatal(err)
	}
	key, err := base64.StdEncoding.DecodeString(public.PublicKey)
	if err != nil || len(key) != ed25519.PublicKeySize {
		t.Fatal("invalid public key representation")
	}
	id, err := core.DeviceIDForPublicKey(ed25519.PublicKey(key))
	if err != nil || public.DeviceID != id {
		t.Fatal("public identity not bound to its key")
	}
	if _, err := (Identity{}).Public(); err == nil {
		t.Fatal("empty identity was exposed as valid")
	}
}
