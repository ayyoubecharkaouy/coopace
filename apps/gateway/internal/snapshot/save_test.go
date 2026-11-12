package snapshot

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestSaveExclusivePublishesReadablePrivateSnapshotAndNeverOverwrites(t *testing.T) {
	imported, err := Read(context.Background(), bytes.NewReader(snapshotFixture(t)))
	if err != nil {
		t.Fatal(err)
	}
	report := Report{Version: "test", OS: "linux", Architecture: "amd64", Snapshot: imported.Snapshot}
	directory := t.TempDir()
	target := filepath.Join(directory, "baseline.json")
	if err := SaveExclusive(context.Background(), target, report); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(target)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := Read(context.Background(), bytes.NewReader(data)); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(target)
	if err != nil {
		t.Fatal(err)
	}
	if runtime.GOOS != "windows" && info.Mode().Perm() != 0600 {
		t.Fatalf("file permissions: %v", info.Mode())
	}
	if err := SaveExclusive(context.Background(), target, report); err == nil {
		t.Fatal("overwrote baseline")
	}
	unchanged, _ := os.ReadFile(target)
	if !bytes.Equal(data, unchanged) {
		t.Fatal("original baseline modified")
	}
	link := filepath.Join(directory, "link.json")
	if err := os.Symlink(target, link); err == nil {
		if err := SaveExclusive(context.Background(), link, report); err == nil {
			t.Fatal("followed destination symlink")
		}
	}
	entries, _ := os.ReadDir(directory)
	for _, entry := range entries {
		if entry.Name() != "baseline.json" && entry.Name() != "link.json" {
			t.Fatalf("temporary file leaked: %s", entry.Name())
		}
	}
}

func TestSaveExclusiveRefusesInvalidReportAndCancellationBeforePublication(t *testing.T) {
	target := filepath.Join(t.TempDir(), "baseline.json")
	if err := SaveExclusive(context.Background(), target, Report{}); err == nil {
		t.Fatal("invalid report saved")
	}
	if _, err := os.Stat(target); !os.IsNotExist(err) {
		t.Fatal("invalid destination created")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := SaveExclusive(ctx, target, Report{}); err != context.Canceled {
		t.Fatalf("cancellation ignored: %v", err)
	}
	if _, err := os.Stat(target); !os.IsNotExist(err) {
		t.Fatal("cancelled destination created")
	}
}
