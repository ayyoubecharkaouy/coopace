// Package group manages explicit peer approvals and bounded authenticated exchanges.
package group

import (
	"fmt"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
	"github.com/ayyoubecharkaouy/coopace/packages/protocol"
)

// DeviceFromHello converts a decoded and session-bound hello to domain data.
// Network authentication and admission must happen before calling this boundary.
func DeviceFromHello(message protocol.Message) (core.Device, error) {
	if message.Kind != protocol.HelloKind || message.Hello == nil {
		return core.Device{}, fmt.Errorf("device description requires a hello")
	}
	hello := message.Hello
	device := core.Device{
		ID: core.DeviceID(message.SenderID), Name: hello.Name, OS: core.OperatingSystem(hello.OS),
		Roles: make([]core.Role, 0, len(hello.Roles)), Capabilities: make([]core.Capability, 0, len(hello.Capabilities)),
	}
	for _, role := range hello.Roles {
		device.Roles = append(device.Roles, core.Role(role))
	}
	for _, capability := range hello.Capabilities {
		device.Capabilities = append(device.Capabilities, core.Capability(capability))
	}
	if err := device.Validate(); err != nil {
		return core.Device{}, err
	}
	return device, nil
}
