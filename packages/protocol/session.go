package protocol

import "fmt"

// Session validates application ordering and binding, not cryptographic identity.
// Construct it only with a group selected locally and a peer authenticated and
// trusted by the transport. Never derive those expected values from an incoming
// message. One connection owns one Session and serializes calls to Next.
type Session struct {
	groupID      string
	peerID       string
	lastSequence uint64
}

func NewSession(groupID, authenticatedPeerID string) (*Session, error) {
	if !validID(groupID) || !validFingerprint(authenticatedPeerID) {
		return nil, fmt.Errorf("invalid expected group or authenticated peer ID")
	}
	return &Session{groupID: groupID, peerID: authenticatedPeerID}, nil
}

func (s *Session) Next(data []byte) (Message, error) {
	message, err := Decode(data)
	if err != nil {
		return Message{}, err
	}
	if message.GroupID != s.groupID || message.SenderID != s.peerID || message.Sequence != s.lastSequence+1 {
		return Message{}, fmt.Errorf("message does not match session group, authenticated peer or next sequence")
	}
	if (s.lastSequence == 0 && message.Kind != HelloKind) || (s.lastSequence > 0 && message.Kind == HelloKind) {
		return Message{}, fmt.Errorf("session requires exactly one initial hello")
	}
	s.lastSequence = message.Sequence
	return message, nil
}
