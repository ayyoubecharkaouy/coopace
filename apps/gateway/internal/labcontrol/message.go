// Package labcontrol defines the internal, one-session CAKE control protocol.
// It supplies no CLI, tc execution, privileged launcher or cleanup mechanism.
package labcontrol

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"

	"github.com/ayyoubecharkaouy/coopace/internal/strictjson"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

const (
	MaxRequestBytes = 4096
	MaxCommandBytes = 1024
)

// Request can only be populated through the strict internal decoder. Its zero
// value is invalid. Session identity is still checked against the trusted launch.
type Request struct {
	session   string
	reference core.CakeReferenceID
	namespace linux.NetworkNamespaceIdentity
	valid     bool
}

func (r Request) SessionID() string                                 { return r.session }
func (r Request) Reference() core.CakeReferenceID                   { return r.reference }
func (r Request) NamespaceIdentity() linux.NetworkNamespaceIdentity { return r.namespace }

type Command struct {
	session string
	action  string
}

func (c Command) Action() string    { return c.action }
func (c Command) SessionID() string { return c.session }

func validSession(value string) bool {
	if len(value) != 8 {
		return false
	}
	for _, c := range value {
		if c != '_' && (c < 'a' || c > 'z') && (c < '0' || c > '9') {
			return false
		}
	}
	return true
}

// readFrame bounds allocation before reading the payload. Deadline/cancellation
// of a blocked reader belongs to its transport (WorkerTransport on Linux).
func readFrame(input io.Reader, limit uint32) ([]byte, error) {
	var prefix [4]byte
	if _, err := io.ReadFull(input, prefix[:]); err != nil {
		return nil, err
	}
	size := binary.BigEndian.Uint32(prefix[:])
	if size == 0 || size > limit {
		return nil, fmt.Errorf("invalid laboratory frame size")
	}
	data := make([]byte, size)
	if _, err := io.ReadFull(input, data); err != nil {
		return nil, err
	}
	if err := strictjson.Check(data, int(limit)); err != nil {
		return nil, err
	}
	return data, nil
}

func decode(data []byte, output any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	return decoder.Decode(output)
}

func ReadRequest(input io.Reader) (Request, error) {
	data, err := readFrame(input, MaxRequestBytes)
	if err != nil {
		return Request{}, err
	}
	var value struct {
		Schema    *int                  `json:"schema_version"`
		Kind      *string               `json:"kind"`
		Session   *string               `json:"session_id"`
		Purpose   *string               `json:"purpose"`
		Reference *core.CakeReferenceID `json:"reference"`
		Namespace *struct {
			Device *uint64 `json:"device"`
			Inode  *uint64 `json:"inode"`
		} `json:"namespace_identity"`
	}
	if err := decode(data, &value); err != nil {
		return Request{}, err
	}
	if value.Schema == nil || *value.Schema != 1 || value.Kind == nil || *value.Kind != "lab_cake_worker_request" ||
		value.Session == nil || !validSession(*value.Session) || value.Purpose == nil || *value.Purpose != "cake_down_control" ||
		value.Reference == nil || *value.Reference != core.CakeReferenceIPv4LabV1 || value.Namespace == nil ||
		value.Namespace.Device == nil || value.Namespace.Inode == nil {
		return Request{}, fmt.Errorf("incomplete or incompatible laboratory request")
	}
	return Request{session: *value.Session, reference: *value.Reference,
		namespace: linux.NetworkNamespaceIdentity{Device: *value.Namespace.Device, Inode: *value.Namespace.Inode}, valid: true}, nil
}

func ReadCommand(input io.Reader) (Command, error) {
	data, err := readFrame(input, MaxCommandBytes)
	if err != nil {
		return Command{}, err
	}
	var value struct {
		Schema  *int    `json:"schema_version"`
		Kind    *string `json:"kind"`
		Session *string `json:"session_id"`
		Action  *string `json:"action"`
	}
	if err := decode(data, &value); err != nil {
		return Command{}, err
	}
	if value.Schema == nil || *value.Schema != 1 || value.Kind == nil || *value.Kind != "lab_cake_worker_control" ||
		value.Session == nil || !validSession(*value.Session) || value.Action == nil || (*value.Action != "apply" && *value.Action != "finish") {
		return Command{}, fmt.Errorf("incomplete or incompatible laboratory control")
	}
	return Command{session: *value.Session, action: *value.Action}, nil
}
