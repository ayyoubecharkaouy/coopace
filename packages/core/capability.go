package core

// Capability describes a technical ability, independently of consent or activity.
type Capability string

const (
	CapabilityObserveLocalTraffic  Capability = "observe_local_traffic"
	CapabilityManageGatewayTraffic Capability = "manage_gateway_traffic"
	CapabilityRelayTraffic         Capability = "relay_traffic"
)

func (c Capability) valid() bool {
	switch c {
	case CapabilityObserveLocalTraffic, CapabilityManageGatewayTraffic, CapabilityRelayTraffic:
		return true
	default:
		return false
	}
}
