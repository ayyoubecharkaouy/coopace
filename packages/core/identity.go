package core

import (
	"crypto/ed25519"
	"crypto/sha256"
	"fmt"
)

// DeviceIDForPublicKey binds an identifier to public key bytes, not to trust or consent.
func DeviceIDForPublicKey(publicKey ed25519.PublicKey) (DeviceID, error) {
	if len(publicKey) != ed25519.PublicKeySize {
		return "", fmt.Errorf("invalid Ed25519 public key length")
	}
	digest := sha256.Sum256(publicKey)
	return DeviceID(fmt.Sprintf("ed25519:%x", digest)), nil
}
