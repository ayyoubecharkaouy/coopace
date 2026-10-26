//go:build linux && !android

package identity

import (
	"os"
	"path/filepath"
	"testing"
)

func TestPersistentIdentityIsStableAndPrivate(t *testing.T) {
	directory := filepath.Join(t.TempDir(), "state")
	first, err := Init(directory)
	if err != nil {
		t.Fatal(err)
	}
	second, err := Init(directory)
	if err != nil {
		t.Fatal(err)
	}
	loaded, err := Load(directory)
	if err != nil {
		t.Fatal(err)
	}
	a, _ := first.Public()
	b, _ := second.Public()
	c, _ := loaded.Public()
	if a != b || a != c {
		t.Fatal("reinitialization or load changed identity")
	}
	key, err := os.Stat(filepath.Join(directory, keyFile))
	if err != nil || key.Mode().Perm() != 0600 {
		t.Fatal("key does not have private permissions")
	}
	folder, err := os.Stat(directory)
	if err != nil || folder.Mode().Perm() != 0700 {
		t.Fatal("state folder does not have private permissions")
	}
}

func TestCorruptedIdentityIsNeverReplaced(t *testing.T) {
	directory := privateDirectory(t)
	path := filepath.Join(directory, keyFile)
	if err := os.WriteFile(path, []byte("incomplete key"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := Init(directory); err == nil {
		t.Fatal("corrupted identity silently repaired")
	}
	contents, err := os.ReadFile(path)
	if err != nil || string(contents) != "incomplete key" {
		t.Fatal("existing key contents changed")
	}
}

func TestUnsafeStorageAndSymlinkAreRejected(t *testing.T) {
	directory := privateDirectory(t)
	if _, err := Init(directory); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(directory, keyFile)
	if err := os.Chmod(path, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(directory); err == nil {
		t.Fatal("publicly readable key accepted")
	}
	if err := os.Chmod(path, 0600); err != nil {
		t.Fatal(err)
	}
	other := privateDirectory(t)
	if err := os.Symlink(path, filepath.Join(other, keyFile)); err != nil {
		t.Fatal(err)
	}
	if _, err := Init(other); err == nil {
		t.Fatal("symlink key accepted")
	}
	if err := os.Chmod(directory, 0755); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(directory); err == nil {
		t.Fatal("non-private state folder accepted")
	}
}

func TestShowingMissingIdentityDoesNotCreateState(t *testing.T) {
	directory := filepath.Join(t.TempDir(), "missing")
	if _, err := Load(directory); err == nil {
		t.Fatal("missing identity unexpectedly loaded")
	}
	if _, err := os.Stat(directory); !os.IsNotExist(err) {
		t.Fatal("load created state")
	}
}

func privateDirectory(t *testing.T) string {
	t.Helper()
	directory := filepath.Join(t.TempDir(), "private-state")
	if err := os.Mkdir(directory, 0700); err != nil {
		t.Fatal(err)
	}
	return directory
}
