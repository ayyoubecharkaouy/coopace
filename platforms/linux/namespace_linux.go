//go:build linux && !android

package linux

import (
	"fmt"
	"os"
	"runtime"
	"syscall"
)

// NS_GET_NSTYPE = _IO(0xb7, 3), checked against Linux amd64 UAPI nsfs.h.
const nsGetNSTypeAMD64 = 0xb703

func readNetworkNamespaceIdentity(file *os.File) (NetworkNamespaceIdentity, error) {
	if file == nil {
		return NetworkNamespaceIdentity{}, fmt.Errorf("network namespace descriptor is absent")
	}
	info, err := file.Stat()
	if err != nil {
		return NetworkNamespaceIdentity{}, err
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return NetworkNamespaceIdentity{}, fmt.Errorf("network namespace stat is unavailable")
	}
	kind, _, errno := syscall.Syscall(syscall.SYS_IOCTL, file.Fd(), nsGetNSTypeAMD64, 0)
	runtime.KeepAlive(file)
	if errno != 0 {
		return NetworkNamespaceIdentity{}, fmt.Errorf("NS_GET_NSTYPE: %w", errno)
	}
	if kind != syscall.CLONE_NEWNET {
		return NetworkNamespaceIdentity{}, fmt.Errorf("descriptor does not refer to a network namespace")
	}
	return NetworkNamespaceIdentity{Device: uint64(stat.Dev), Inode: uint64(stat.Ino)}, nil
}

// VerifyLabNamespace borrows, but never closes, the supplied descriptors. It
// opens the calling thread's current namespace read-only and closes that local
// handle. The trusted supervisor must supply its actual original namespace and
// prove ownership of the retained target; this check is not that attestation.
func VerifyLabNamespace(expected NetworkNamespaceIdentity, retained, original *os.File) error {
	if runtime.GOARCH != "amd64" {
		return fmt.Errorf("network namespace descriptor checks currently support Linux amd64 only")
	}
	current, err := os.Open("/proc/thread-self/ns/net")
	if err != nil {
		return err
	}
	defer current.Close()
	return verifyLabNamespaceFiles(expected, retained, current, original, readNetworkNamespaceIdentity)
}

func verifyLabNamespaceFiles(expected NetworkNamespaceIdentity, retained, current, original *os.File,
	read func(*os.File) (NetworkNamespaceIdentity, error)) error {
	identities := make([]NetworkNamespaceIdentity, 0, 3)
	for _, file := range []*os.File{retained, current, original} {
		identity, err := read(file)
		if err != nil {
			return err
		}
		identities = append(identities, identity)
	}
	return validateLabNamespaceIdentities(expected, identities[0], identities[1], identities[2])
}
