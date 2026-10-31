package linux

import "time"

// LabToolSpec is supplied by the trusted launcher, never by a plan/scenario.
// Path must be absolute and canonical; SHA256 pins the executable's contents.
type LabToolSpec struct{ Path, SHA256 string }

type CakeLabLink struct {
	LoopbackIndex, Index, PeerIndex, MTU uint64
	MAC                                  string
}

// LabToolCall retains bounded source bytes, including failed calls. This is an
// internal Go record, not a public JSON report or an attestation of cleanup.
type LabToolCall struct {
	Path, SHA256                     string
	Arguments                        []string
	StartedAt                        time.Time
	Duration                         time.Duration
	PID                              int
	ExitCode                         *int
	Stdout, Stderr                   []byte
	StdoutTruncated, StderrTruncated bool
	Error                            string
}

type CakeLabEvidence struct {
	Producer     CakeProducer
	Link         *CakeLabLink
	AddAttempted bool
	Calls        []LabToolCall
	State, Error string
}
