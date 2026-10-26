package core

// GatewayReading distinguishes a successful empty/false result from missing data.
// It describes an observation, never an authorization or readiness decision.
type GatewayReading[T any] struct {
	Available bool
	Value     T
	Reason    string
}

type GatewayInterface struct {
	Name     string
	Index    int
	MTU      int
	Up       bool
	Loopback bool
}

type GatewayTool struct {
	Name      string
	Path      string
	Available bool
}

// GatewayDefaultRoute deliberately omits IP addresses. Interfaces may be empty
// for rejecting routes or unresolved nexthop references; this is not an egress
// selection or a complete policy-routing analysis.
type GatewayDefaultRoute struct {
	Table             string
	Kind              string
	Interfaces        []string
	UnresolvedNexthop bool
}

type GatewayQueue struct {
	Interface string
	Kind      string
	Handle    string
	Parent    string
	Root      bool
}

type GatewayInventory struct {
	Interfaces     GatewayReading[[]GatewayInterface]
	IPv4Forwarding GatewayReading[bool]
	IPv6Forwarding GatewayReading[bool]
	NetAdmin       GatewayReading[bool]
	IPv4Defaults   GatewayReading[[]GatewayDefaultRoute]
	IPv6Defaults   GatewayReading[[]GatewayDefaultRoute]
	Queues         GatewayReading[[]GatewayQueue]
	Tools          []GatewayTool
}
