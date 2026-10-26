package core

import (
	"crypto/ed25519"
	"crypto/sha256"
	"fmt"
	"strings"
	"unicode"
	"unicode/utf8"
)

// DeviceIDForPublicKey binds an identifier to public key bytes, not to trust or consent.
func DeviceIDForPublicKey(publicKey ed25519.PublicKey) (DeviceID, error) {
	if len(publicKey) != ed25519.PublicKeySize {
		return "", fmt.Errorf("invalid Ed25519 public key length")
	}
	digest := sha256.Sum256(publicKey)
	return DeviceID(fmt.Sprintf("ed25519:%x", digest)), nil
}

// GroupConsent is a local permission record, not proof of admission by a peer.
// Joining, sharing observations and using a device as relay are separate choices.
type GroupConsent struct {
	GroupID           string
	DeviceID          DeviceID
	Join              bool
	ShareObservations bool
	AllowRelay        bool
}

func (c GroupConsent) Validate() error {
	if len(c.GroupID) == 0 || len(c.GroupID) > 128 || !utf8.ValidString(c.GroupID) || strings.ContainsFunc(c.GroupID, func(r rune) bool {
		return unicode.IsSpace(r) || unicode.IsControl(r)
	}) {
		return fmt.Errorf("invalid group ID")
	}
	if err := c.DeviceID.Validate(); err != nil {
		return err
	}
	if !c.Join && (c.ShareObservations || c.AllowRelay) {
		return fmt.Errorf("sharing observations or allowing a relay requires consent to join")
	}
	return nil
}

func (c GroupConsent) AllowsObservationSharing(groupID string, deviceID DeviceID) bool {
	return c.Validate() == nil && c.Join && c.ShareObservations && c.GroupID == groupID && c.DeviceID == deviceID
}
