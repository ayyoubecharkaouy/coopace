package linux

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"path/filepath"
	"strings"
	"time"
	"unicode/utf8"
)

// LabToolSpec is supplied by the trusted launcher, never by a plan/scenario.
// Path must be absolute and canonical; SHA256 pins the executable's contents.
type LabToolSpec struct{ Path, SHA256 string }

// LabToolObserver persists intent before dispatch and the bounded result before
// allowing the next operation. A recording error must stop the control.
type LabToolObserver interface {
	ToolIntent(LabToolSpec, []string) error
	ToolResult(LabToolCall) error
}

// Validate checks the tool declaration without reading or executing a file.
func (spec LabToolSpec) Validate() error {
	digest, err := hex.DecodeString(spec.SHA256)
	if len(spec.Path) > 4096 || !utf8.ValidString(spec.Path) || strings.ContainsRune(spec.Path, 0) || !filepath.IsAbs(spec.Path) || filepath.Clean(spec.Path) != spec.Path || err != nil || len(digest) != sha256.Size || spec.SHA256 != strings.ToLower(spec.SHA256) {
		return fmt.Errorf("absolute canonical tool path and lowercase SHA-256 required")
	}
	return nil
}

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

func cloneLabToolCall(call LabToolCall) LabToolCall {
	call.Arguments = append([]string(nil), call.Arguments...)
	call.Stdout = append([]byte(nil), call.Stdout...)
	call.Stderr = append([]byte(nil), call.Stderr...)
	if call.ExitCode != nil {
		code := *call.ExitCode
		call.ExitCode = &code
	}
	return call
}
