//go:build !linux || android

package linux

import (
	"fmt"
	"os"
)

func VerifyLabNamespace(_ NetworkNamespaceIdentity, _, _ *os.File) error {
	return fmt.Errorf("network namespace descriptor checks require Linux amd64")
}

func InspectNetworkNamespaceDescriptor(_ *os.File) (NetworkNamespaceIdentity, error) {
	return NetworkNamespaceIdentity{}, fmt.Errorf("network namespace descriptor checks require Linux amd64")
}
