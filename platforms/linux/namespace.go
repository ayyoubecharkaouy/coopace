package linux

import "fmt"

// NetworkNamespaceIdentity identifies a kernel namespace object, not a path or
// an authorization. Observations must come from retained network-namespace FDs.
type NetworkNamespaceIdentity struct {
	Device uint64
	Inode  uint64
}

func validateLabNamespaceIdentities(expected, retained, current, original NetworkNamespaceIdentity) error {
	for _, identity := range []NetworkNamespaceIdentity{expected, retained, current, original} {
		if identity.Inode == 0 {
			return fmt.Errorf("network namespace identity is unavailable")
		}
	}
	if expected != retained || retained != current {
		return fmt.Errorf("current network namespace does not match the retained session namespace")
	}
	if current == original {
		return fmt.Errorf("original supervisor network namespace is outside the disposable laboratory")
	}
	return nil
}
