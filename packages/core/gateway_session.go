package core

import (
	"encoding/hex"
	"fmt"
)

// GatewaySession is the decision side of a single owned-lab session. It never
// executes commands and never declares restoration: that belongs to the
// independent supervisor after the decision process has stopped.
type GatewaySession struct {
	phase        string
	beforeSHA256 string
	sequence     uint64
}

func NewGatewaySession(reference CakeReferenceID, beforeSHA256 string, localLabConsent bool) (*GatewaySession, error) {
	decoded, err := hex.DecodeString(beforeSHA256)
	if reference != CakeReferenceIPv4LabV1 || err != nil || len(decoded) != 32 || hex.EncodeToString(decoded) != beforeSHA256 || !localLabConsent {
		return nil, fmt.Errorf("owned lab reference, SHA-256 and explicit local consent required")
	}
	return &GatewaySession{phase: "ready", beforeSHA256: beforeSHA256}, nil
}

func (s *GatewaySession) Phase() string { return s.phase }

// Advance consumes exactly one ordered command. Any violation permanently
// fails the session; retrying an uncertain apply is deliberately unsupported.
func (s *GatewaySession) Advance(sequence uint64, action, beforeSHA256 string) error {
	if s.phase == "" || s.phase == "failed" || sequence != s.sequence+1 || beforeSHA256 != s.beforeSHA256 {
		s.phase = "failed"
		return fmt.Errorf("session binding or sequence mismatch")
	}
	next := ""
	switch {
	case s.phase == "ready" && action == "begin":
		next = "apply_requested"
	case s.phase == "apply_requested" && action == "applied":
		next = "applied"
	case s.phase == "applied" && action == "stop":
		next = "release_requested"
	}
	if next == "" {
		s.phase = "failed"
		return fmt.Errorf("command outside session lifecycle")
	}
	s.sequence, s.phase = sequence, next
	return nil
}
