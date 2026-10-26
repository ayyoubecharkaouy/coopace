// Package identity manages the agent's local Ed25519 identity.
package identity

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"fmt"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

// Identity deliberately keeps its private key out of public output structures.
type Identity struct {
	privateKey ed25519.PrivateKey
}

type Public struct {
	DeviceID  core.DeviceID
	PublicKey string
}

func generate() (Identity, error) {
	_, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return Identity{}, err
	}
	return Identity{privateKey: privateKey}, nil
}

func (i Identity) Public() (Public, error) {
	if len(i.privateKey) != ed25519.PrivateKeySize {
		return Public{}, fmt.Errorf("identity has no valid private key")
	}
	publicKey := i.privateKey.Public().(ed25519.PublicKey)
	id, err := core.DeviceIDForPublicKey(publicKey)
	if err != nil {
		return Public{}, err
	}
	return Public{DeviceID: id, PublicKey: base64.StdEncoding.EncodeToString(publicKey)}, nil
}
