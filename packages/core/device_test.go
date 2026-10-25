package core_test

import (
	"fmt"
	"reflect"
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func sampleDevice() core.Device {
	return core.Device{
		ID:   "device-01",
		Name: "Bureau été",
		OS:   core.OSLinux,
		Roles: []core.Role{
			core.RoleAgent,
		},
	}
}

func TestDeviceValidateAcceptedDescriptions(t *testing.T) {
	tests := []struct {
		name   string
		change func(*core.Device)
	}{
		{"linux agent before capability assessment", func(d *core.Device) {}},
		{"windows agent", func(d *core.Device) { d.OS = core.OSWindows }},
		{"android observer", func(d *core.Device) {
			d.OS = core.OSAndroid
			d.Capabilities = []core.Capability{core.CapabilityObserveLocalTraffic}
		}},
		{"gateway without agent role", func(d *core.Device) {
			d.Roles = []core.Role{core.RoleGateway}
			d.Capabilities = []core.Capability{core.CapabilityManageGatewayTraffic}
		}},
		{"combined gateway and agent", func(d *core.Device) {
			d.Roles = []core.Role{core.RoleAgent, core.RoleGateway}
			d.Capabilities = []core.Capability{
				core.CapabilityObserveLocalTraffic,
				core.CapabilityManageGatewayTraffic,
				core.CapabilityRelayTraffic,
			}
		}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			device := sampleDevice()
			tt.change(&device)
			if err := device.Validate(); err != nil {
				t.Fatalf("valid description rejected: %v", err)
			}
		})
	}
}

func TestDeviceValidateRejectsInconsistentDescriptions(t *testing.T) {
	tests := []struct {
		name   string
		change func(*core.Device)
		want   string
	}{
		{"missing ID", func(d *core.Device) { d.ID = "" }, "device ID"},
		{"ID with whitespace", func(d *core.Device) { d.ID = "device 01" }, "device ID"},
		{"ID with Unicode whitespace", func(d *core.Device) { d.ID = "device\u00a001" }, "device ID"},
		{"ID with control character", func(d *core.Device) { d.ID = "device\x0001" }, "device ID"},
		{"blank name", func(d *core.Device) { d.Name = " \t" }, "device name"},
		{"name with newline", func(d *core.Device) { d.Name = "desktop\nother" }, "device name"},
		{"missing OS", func(d *core.Device) { d.OS = "" }, "operating system"},
		{"unknown OS", func(d *core.Device) { d.OS = "unsupported" }, "operating system"},
		{"missing role", func(d *core.Device) { d.Roles = nil }, "at least one role"},
		{"unknown role", func(d *core.Device) { d.Roles = []core.Role{"leader"} }, "unknown role"},
		{"duplicate role", func(d *core.Device) {
			d.Roles = []core.Role{core.RoleAgent, core.RoleAgent}
		}, "duplicate role"},
		{"unknown capability", func(d *core.Device) {
			d.Capabilities = []core.Capability{"universal_acceleration"}
		}, "unknown capability"},
		{"duplicate capability", func(d *core.Device) {
			d.Capabilities = []core.Capability{core.CapabilityObserveLocalTraffic, core.CapabilityObserveLocalTraffic}
		}, "duplicate capability"},
		{"gateway capability without gateway role", func(d *core.Device) {
			d.Capabilities = []core.Capability{core.CapabilityManageGatewayTraffic}
		}, "requires the gateway role"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			device := sampleDevice()
			tt.change(&device)
			err := device.Validate()
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("Validate() = %v, want error containing %q", err, tt.want)
			}
		})
	}
}

func TestDeviceValidateDoesNotMutateDescription(t *testing.T) {
	device := sampleDevice()
	device.Roles = []core.Role{core.RoleGateway, core.RoleAgent}
	device.Capabilities = []core.Capability{core.CapabilityRelayTraffic, core.CapabilityManageGatewayTraffic}
	want := device
	want.Roles = append([]core.Role(nil), device.Roles...)
	want.Capabilities = append([]core.Capability(nil), device.Capabilities...)
	if err := device.Validate(); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(device, want) {
		t.Fatalf("validation changed the description: got %+v, want %+v", device, want)
	}
}

func ExampleDevice_Validate() {
	device := core.Device{
		ID:    "device-01",
		Name:  "PC Windows",
		OS:    core.OSWindows,
		Roles: []core.Role{core.RoleAgent},
	}
	fmt.Println(device.Validate())
	// Output: <nil>
}
