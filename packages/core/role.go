package core

// Role describes an application role on a device. Roles can be combined.
type Role string

const (
	RoleAgent   Role = "agent"
	RoleGateway Role = "gateway"
)

func (r Role) valid() bool {
	return r == RoleAgent || r == RoleGateway
}
