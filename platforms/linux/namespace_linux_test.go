//go:build linux && !android

package linux

import (
	"errors"
	"os"
	"runtime"
	"testing"
)

func TestNamespaceDescriptorMappingWithSimulatedKernelObservations(t *testing.T) {
	target := NetworkNamespaceIdentity{Device: 11, Inode: 21}
	original := NetworkNamespaceIdentity{Device: 11, Inode: 10}
	retained, current, parent := &os.File{}, &os.File{}, &os.File{}
	read := func(file *os.File) (NetworkNamespaceIdentity, error) {
		if file == parent {
			return original, nil
		}
		return target, nil
	}
	if err := verifyLabNamespaceFiles(target, retained, current, parent, read); err != nil {
		t.Fatal(err)
	}
	errRead := errors.New("descriptor no longer valid")
	for _, fail := range []*os.File{retained, current, parent} {
		reader := func(file *os.File) (NetworkNamespaceIdentity, error) {
			if file == fail {
				return NetworkNamespaceIdentity{}, errRead
			}
			return read(file)
		}
		if err := verifyLabNamespaceFiles(target, retained, current, parent, reader); !errors.Is(err, errRead) {
			t.Fatalf("descriptor error ignored: %v", err)
		}
	}
}

func TestRealNamespaceDescriptorsAreReadOnlyAndOriginalNamespaceIsRejected(t *testing.T) {
	if runtime.GOARCH != "amd64" {
		t.Skip("native descriptor verification currently supports amd64")
	}
	current, err := os.Open("/proc/thread-self/ns/net")
	if err != nil {
		t.Skipf("namespace descriptor unavailable: %v", err)
	}
	defer current.Close()
	identity, err := readNetworkNamespaceIdentity(current)
	if err != nil {
		t.Skipf("read-only namespace ioctl unavailable: %v", err)
	}
	if identity.Inode == 0 {
		t.Fatal("real namespace identity missing")
	}
	if err := VerifyLabNamespace(identity, current, current); err == nil {
		t.Fatal("supervisor original namespace admitted as disposable target")
	}
	if _, err := current.Stat(); err != nil {
		t.Fatal("borrowed descriptor closed")
	}
	pid, err := os.Open("/proc/thread-self/ns/pid")
	if err != nil {
		t.Fatal(err)
	}
	defer pid.Close()
	if _, err := readNetworkNamespaceIdentity(pid); err == nil {
		t.Fatal("PID namespace admitted as network namespace")
	}
}

func TestNamespaceChecksRejectAbsentClosedAndOrdinaryDescriptors(t *testing.T) {
	if runtime.GOARCH != "amd64" {
		t.Skip("native descriptor verification currently supports amd64")
	}
	if _, err := readNetworkNamespaceIdentity(nil); err == nil {
		t.Fatal("absent descriptor accepted")
	}
	file, err := os.CreateTemp(t.TempDir(), "ordinary")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := readNetworkNamespaceIdentity(file); err == nil {
		t.Fatal("ordinary file admitted as namespace")
	}
	file.Close()
	if _, err := readNetworkNamespaceIdentity(file); err == nil {
		t.Fatal("closed descriptor accepted")
	}
}
