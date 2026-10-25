package core

import (
	"fmt"
	"slices"
	"strings"
	"unicode"
	"unicode/utf8"
)

// DeviceID is an opaque local identifier, not a hostname or a network identity.
// Its generation and persistence are outside this package's current scope.
type DeviceID string

// OperatingSystem identifies one of the product's target platforms.
type OperatingSystem string

const (
	OSLinux   OperatingSystem = "linux"
	OSWindows OperatingSystem = "windows"
	OSAndroid OperatingSystem = "android"
)

func (os OperatingSystem) valid() bool {
	return os == OSLinux || os == OSWindows || os == OSAndroid
}

// Device is a description, not a declaration of live support on its platform.
// Roles may be combined; capabilities may be empty when not yet assessed.
// Domain fields deliberately have no wire-format annotations: protocol messages
// and their validation belong to the protocol package and application boundary.
type Device struct {
	ID           DeviceID
	Name         string
	OS           OperatingSystem
	Roles        []Role
	Capabilities []Capability
}

// Validate checks the description's consistency without changing it or doing I/O.
// Callers must validate a description again after modifying its exported fields.
func (d Device) Validate() error {
	if d.ID == "" || !utf8.ValidString(string(d.ID)) || strings.ContainsFunc(string(d.ID), func(r rune) bool {
		return unicode.IsSpace(r) || unicode.IsControl(r)
	}) {
		return fmt.Errorf("device ID must be non-empty valid UTF-8 and contain no whitespace or control characters")
	}
	if !utf8.ValidString(d.Name) || strings.TrimSpace(d.Name) == "" || strings.ContainsFunc(d.Name, unicode.IsControl) {
		return fmt.Errorf("device name must be non-blank valid UTF-8 and contain no control characters")
	}
	if !d.OS.valid() {
		return fmt.Errorf("unsupported operating system: %q", d.OS)
	}
	if len(d.Roles) == 0 {
		return fmt.Errorf("device must declare at least one role")
	}

	roles := make(map[Role]struct{}, len(d.Roles))
	for _, role := range d.Roles {
		if !role.valid() {
			return fmt.Errorf("unknown role: %q", role)
		}
		if _, exists := roles[role]; exists {
			return fmt.Errorf("duplicate role: %q", role)
		}
		roles[role] = struct{}{}
	}

	capabilities := make(map[Capability]struct{}, len(d.Capabilities))
	for _, capability := range d.Capabilities {
		if !capability.valid() {
			return fmt.Errorf("unknown capability: %q", capability)
		}
		if _, exists := capabilities[capability]; exists {
			return fmt.Errorf("duplicate capability: %q", capability)
		}
		capabilities[capability] = struct{}{}
	}

	if slices.Contains(d.Capabilities, CapabilityManageGatewayTraffic) && !slices.Contains(d.Roles, RoleGateway) {
		return fmt.Errorf("managing gateway traffic requires the gateway role")
	}
	return nil
}
