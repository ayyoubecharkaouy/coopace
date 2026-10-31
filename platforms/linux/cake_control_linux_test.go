//go:build linux && !android

package linux

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

type cakeToolTestConfig struct{ Mode, Fixture, Folder string }

// The fake ELF tools handle fixed ip/tc arguments before testing's flag parser.
// syscall.Exit avoids the race runtime's one-second exit delay in every tool;
// races in the production runner/backend remain checked by the parent test.
func TestMain(m *testing.M) {
	if strings.HasPrefix(filepath.Base(os.Args[0]), "coopace-test-") {
		syscall.Exit(fakeCakeTool())
	}
	os.Exit(m.Run())
}

func fakeCakeTool() int {
	var config cakeToolTestConfig
	raw, err := os.ReadFile(os.Args[0] + ".json")
	if err != nil || json.Unmarshal(raw, &config) != nil {
		return 2
	}
	tool := strings.TrimPrefix(filepath.Base(os.Args[0]), "coopace-test-")
	args := os.Args[1:]
	// Only C locale is inherited. In particular, no loader or shell environment
	// from the parent can alter the selected verified executable.
	if !reflect.DeepEqual(os.Environ(), []string{"LANG=C", "LC_ALL=C"}) {
		return 2
	}
	entries, err := os.ReadDir("/proc/self/fd")
	if err != nil {
		return 2
	}
	for _, entry := range entries {
		fd, _ := strconv.Atoi(entry.Name())
		if fd < 4 {
			continue
		}
		var stat syscall.Stat_t
		if syscall.Fstat(fd, &stat) == nil {
			kind, _, errno := syscall.Syscall(syscall.SYS_IOCTL, uintptr(fd), nsGetNSTypeAMD64, 0)
			if (errno == 0 && kind == syscall.CLONE_NEWNET) || stat.Mode&syscall.S_IFMT == syscall.S_IFIFO {
				return 2
			}
		}
	}
	log, err := os.OpenFile(filepath.Join(config.Folder, "calls"), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0600)
	if err != nil {
		return 2
	}
	entry, _ := json.Marshal(struct {
		Tool string
		Args []string
		PID  int
	}{tool, args, os.Getpid()})
	if _, err = log.Write(append(entry, '\n')); err != nil {
		return 2
	}
	log.Close()
	output := func(data []byte) int {
		if _, err := os.Stdout.Write(data); err != nil {
			return 2
		}
		return 0
	}
	if tool == "tc" && reflect.DeepEqual(args, []string{"-V"}) {
		switch config.Mode {
		case "wait":
			time.Sleep(10 * time.Second)
			return 2
		case "banner_flood":
			return output(bytes.Repeat([]byte("x"), 513))
		case "banner_exact":
			banner := []byte("tc utility, iproute2-6.1.0\n")
			return output(append(banner, bytes.Repeat([]byte(" "), 512-len(banner))...))
		case "stderr_flood":
			os.Stderr.Write(bytes.Repeat([]byte("x"), cakeOutputLimit+1))
			return 0
		case "wrong_version":
			return output([]byte("tc utility, iproute2-unknown\n"))
		}
		return output([]byte("tc utility, iproute2-6.1.0\n"))
	}
	if tool == "ip" && reflect.DeepEqual(args, []string{"-j", "-d", "link", "show"}) {
		countPath := filepath.Join(config.Folder, "links")
		raw, _ := os.ReadFile(countPath)
		count, _ := strconv.Atoi(string(raw))
		count++
		if os.WriteFile(countPath, []byte(strconv.Itoa(count)), 0600) != nil {
			return 2
		}
		data := labLinksJSON
		if config.Mode == "bad_link" || (config.Mode == "link_changed" && count >= 2) || (config.Mode == "final_link_changed" && count >= 4) {
			data = strings.Replace(data, `"ifindex":2`, `"ifindex":4`, 1)
		}
		if config.Mode == "link_up" {
			data = strings.Replace(data, `"BROADCAST"`, `"UP"`, 1)
		}
		if config.Mode == "stdout_flood" {
			return output(bytes.Repeat([]byte("x"), cakeOutputLimit+1))
		}
		return output([]byte(data))
	}
	if tool == "ip" && reflect.DeepEqual(args, []string{"-j", "address", "show", "dev", "wan"}) {
		data := labAddressesJSON
		if config.Mode == "addressed" {
			data = strings.Replace(data, `"addr_info":[]`, `"addr_info":[{"family":"inet"}]`, 1)
		}
		return output([]byte(data))
	}
	if tool == "tc" && reflect.DeepEqual(args, []string{"-j", "-s", "-r", "qdisc", "show", "dev", "wan"}) {
		_, added := os.Stat(filepath.Join(config.Folder, "added"))
		if added != nil && config.Mode != "occupied" {
			return output([]byte("[]"))
		}
		data, err := os.ReadFile(config.Fixture)
		if err != nil {
			return 2
		}
		links, _ := os.ReadFile(filepath.Join(config.Folder, "links"))
		if config.Mode == "bad_reading" || (config.Mode == "final_bad_reading" && string(links) == "4") {
			data = []byte("[]")
		}
		return output(data)
	}
	reference, _ := LookupCakeReference(core.CakeReferenceIPv4LabV1)
	if tool == "tc" && reflect.DeepEqual(args, reference.AddArguments) {
		if os.WriteFile(filepath.Join(config.Folder, "added"), []byte("effect may exist"), 0600) != nil {
			return 2
		}
		if config.Mode == "failed_add" {
			os.Stderr.WriteString("simulated partial add failure")
			return 7
		}
		return 0
	}
	return 2
}

func testCakeBackend(t *testing.T, mode string) (*LabCakeControl, CakeLabLaunch, string) {
	t.Helper()
	folder := t.TempDir()
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(executable)
	if err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256(data)
	fixture, err := filepath.Abs("testdata/cake/down.json")
	if err != nil {
		t.Fatal(err)
	}
	config, _ := json.Marshal(cakeToolTestConfig{Mode: mode, Fixture: fixture, Folder: folder})
	specs := make([]LabToolSpec, 2)
	for i, name := range []string{"ip", "tc"} {
		path := filepath.Join(folder, "coopace-test-"+name)
		if err := os.WriteFile(path, data, 0700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path+".json", config, 0600); err != nil {
			t.Fatal(err)
		}
		specs[i] = LabToolSpec{Path: path, SHA256: hex.EncodeToString(hash[:])}
	}
	target, err := os.Open("/proc/thread-self/ns/net")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { target.Close() })
	original, err := os.Open("/proc/thread-self/ns/net")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { original.Close() })
	info, _ := target.Stat()
	stat := info.Sys().(*syscall.Stat_t)
	launch := CakeLabLaunch{IP: specs[0], TC: specs[1], Namespace: NetworkNamespaceIdentity{Device: uint64(stat.Dev), Inode: uint64(stat.Ino)}, Target: target, Original: original}
	// Positive namespace acceptance is simulated. The public constructor never
	// supplies this verifier; real original-as-target remains inadmissible.
	verify := func(expected NetworkNamespaceIdentity, target, original *os.File) error {
		for _, file := range []*os.File{target, original} {
			info, err := file.Stat()
			if err != nil {
				return err
			}
			s := info.Sys().(*syscall.Stat_t)
			if expected != (NetworkNamespaceIdentity{Device: uint64(s.Dev), Inode: uint64(s.Ino)}) {
				return fmt.Errorf("descriptor identity mismatch")
			}
		}
		return nil
	}
	backend, err := newLabCakeControl(launch, verify)
	if err != nil {
		t.Fatal(err)
	}
	return backend, launch, folder
}

func TestNativeCakeBackendFixedSequenceEvidenceAndSingleAttempt(t *testing.T) {
	backend, _, folder := testCakeBackend(t, "normal")
	ctx := context.Background()
	if _, err := backend.Prepare(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(folder, "added")); !os.IsNotExist(err) {
		t.Fatal("prepare mutated qdisc")
	}
	raw, profile, err := backend.Apply(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ParseCakeReading(raw, profile); err != nil {
		t.Fatal(err)
	}
	if _, err := backend.Final(ctx); err != nil {
		t.Fatal(err)
	}
	evidence := backend.Evidence()
	if evidence.State != "finished" || !evidence.AddAttempted || evidence.Link == nil || len(evidence.Calls) != 14 {
		t.Fatalf("incomplete trace: %+v", evidence)
	}
	for _, call := range evidence.Calls {
		if call.PID <= 0 || call.ExitCode == nil || *call.ExitCode != 0 || call.Error != "" || call.Duration <= 0 {
			t.Fatalf("invalid call: %+v", call)
		}
		if _, err := os.Stat(fmt.Sprintf("/proc/%d", call.PID)); !os.IsNotExist(err) {
			t.Fatal("tool was not reaped")
		}
	}
	evidence.Calls[0].Arguments[0] = "unsafe"
	evidence.Calls[0].Stdout[0] = 'x'
	*evidence.Calls[0].ExitCode = 99
	evidence.Link.Index = 99
	if current := backend.Evidence(); current.Calls[0].Arguments[0] != "-V" || current.Calls[0].Stdout[0] != 't' || *current.Calls[0].ExitCode != 0 || current.Link.Index != 2 {
		t.Fatal("trace alias escaped")
	}
	if _, _, err := backend.Apply(ctx); err == nil {
		t.Fatal("finished backend replayed")
	}
	if len(backend.Evidence().Calls) != 14 {
		t.Fatal("replay executed a tool")
	}
}

func TestNativeCakeBackendRejectsStateChangesAndPartialFailures(t *testing.T) {
	for _, mode := range []string{"wrong_version", "banner_flood", "stderr_flood", "stdout_flood", "link_up", "addressed", "occupied", "bad_link", "link_changed", "failed_add", "bad_reading", "final_link_changed", "final_bad_reading"} {
		t.Run(mode, func(t *testing.T) {
			backend, _, _ := testCakeBackend(t, mode)
			_, err := backend.Prepare(context.Background())
			if err == nil {
				_, _, err = backend.Apply(context.Background())
			}
			if err == nil {
				_, err = backend.Final(context.Background())
			}
			if err == nil {
				t.Fatal("invalid backend accepted")
			}
			evidence := backend.Evidence()
			count := len(evidence.Calls)
			if evidence.State != "failed" || evidence.Error == "" {
				t.Fatal("failure not retained")
			}
			if _, _, err := backend.Apply(context.Background()); err == nil || len(backend.Evidence().Calls) != count {
				t.Fatal("failed add retried")
			}
			expectedAdd := mode == "failed_add" || mode == "bad_reading" || mode == "final_link_changed" || mode == "final_bad_reading"
			if evidence.AddAttempted != expectedAdd {
				t.Fatalf("incorrect add provenance: %v", evidence.AddAttempted)
			}
			for _, call := range evidence.Calls {
				if len(call.Stdout) > cakeOutputLimit || len(call.Stderr) > cakeOutputLimit {
					t.Fatal("unbounded output")
				}
			}
			if strings.HasSuffix(mode, "flood") {
				last := evidence.Calls[len(evidence.Calls)-1]
				if !errors.Is(err, errCakeOutputLimit) {
					t.Fatal("overflow rejected for the wrong reason", err)
				}
				if mode == "stderr_flood" {
					if !last.StderrTruncated || len(last.Stderr) != cakeOutputLimit {
						t.Fatal("stderr limit not retained")
					}
				} else {
					expected := cakeOutputLimit
					if mode == "banner_flood" {
						expected = 512
					}
					if !last.StdoutTruncated || len(last.Stdout) != expected {
						t.Fatal("stdout limit not retained")
					}
				}
			}
			if mode == "failed_add" {
				last := evidence.Calls[len(evidence.Calls)-1]
				if last.ExitCode == nil || *last.ExitCode != 7 || string(last.Stderr) != "simulated partial add failure" {
					t.Fatal("failed call lost")
				}
			}
		})
	}
}

func TestNativeCakeBackendRechecksExecutableAndNamespaceBeforeAdd(t *testing.T) {
	for _, mode := range []string{"hash", "namespace", "closed_descriptor"} {
		t.Run(mode, func(t *testing.T) {
			backend, launch, _ := testCakeBackend(t, "normal")
			if _, err := backend.Prepare(context.Background()); err != nil {
				t.Fatal(err)
			}
			switch mode {
			case "hash":
				file, err := os.OpenFile(launch.TC.Path, os.O_WRONLY|os.O_APPEND, 0)
				if err != nil {
					t.Fatal(err)
				}
				file.WriteString("changed")
				file.Close()
			case "namespace":
				backend.verify = func(NetworkNamespaceIdentity, *os.File, *os.File) error { return errors.New("binding changed") }
			case "closed_descriptor":
				launch.Target.Close()
			}
			if _, _, err := backend.Apply(context.Background()); err == nil {
				t.Fatal("changed prerequisite accepted")
			}
			if backend.Evidence().AddAttempted {
				t.Fatal("add ran after failed preflight")
			}
		})
	}
}

func TestNativeCakeBackendPublicPathRefusesOriginalNamespaceWithoutTool(t *testing.T) {
	_, launch, folder := testCakeBackend(t, "normal")
	backend, err := NewLabCakeControl(launch)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := backend.Prepare(context.Background()); err == nil {
		t.Fatal("original namespace accepted")
	}
	if len(backend.Evidence().Calls) != 0 {
		t.Fatal("tool ran before native namespace check")
	}
	if _, err := os.Stat(filepath.Join(folder, "calls")); !os.IsNotExist(err) {
		t.Fatal("external tool executed")
	}
	for _, spec := range []LabToolSpec{{Path: "tc", SHA256: launch.TC.SHA256}, {Path: launch.TC.Path, SHA256: "wrong"}} {
		launch.TC = spec
		if _, err := NewLabCakeControl(launch); err == nil {
			t.Fatal("unbound tool accepted")
		}
	}
}

func TestNativeCakeToolAcceptsExactBannerLimit(t *testing.T) {
	backend, _, _ := testCakeBackend(t, "banner_exact")
	if _, err := backend.Prepare(context.Background()); err != nil {
		t.Fatal(err)
	}
	call := backend.Evidence().Calls[0]
	if len(call.Stdout) != 512 || call.StdoutTruncated {
		t.Fatal("exact banner limit rejected or altered")
	}
}

func TestNativeCakeToolDeadlineCancellationAndPinning(t *testing.T) {
	_, launch, _ := testCakeBackend(t, "wait")
	for _, parentLimit := range []time.Duration{150 * time.Millisecond, 5 * time.Second} {
		ctx, cancel := context.WithTimeout(context.Background(), parentLimit)
		call, err := runCakeTool(ctx, launch.TC, []string{"-V"}, 512)
		cancel()
		if !errors.Is(err, context.DeadlineExceeded) || call.PID <= 0 || call.ExitCode == nil || call.Duration > 3*time.Second {
			t.Fatalf("tool not bounded/reaped: %+v %v", call, err)
		}
		if _, err := os.Stat(fmt.Sprintf("/proc/%d", call.PID)); !os.IsNotExist(err) {
			t.Fatal("timed-out child retained")
		}
	}
	_, launch, folder := testCakeBackend(t, "normal")
	link := filepath.Join(folder, "alias")
	if err := os.Symlink(launch.TC.Path, link); err != nil {
		t.Fatal(err)
	}
	launch.TC.Path = link
	if call, err := runCakeTool(context.Background(), launch.TC, []string{"-V"}, 512); err == nil || call.PID != 0 {
		t.Fatal("symlink executable accepted")
	}
	script := filepath.Join(folder, "script")
	data := []byte("#!/bin/sh\nexit 0\n")
	if err := os.WriteFile(script, data, 0700); err != nil {
		t.Fatal(err)
	}
	hash := sha256.Sum256(data)
	if call, err := runCakeTool(context.Background(), LabToolSpec{Path: script, SHA256: hex.EncodeToString(hash[:])}, []string{"-V"}, 512); err == nil || call.PID != 0 {
		t.Fatal("shell interpreter accepted")
	}
}

func TestPinnedCakeToolRejectsFIFOWithoutWaitingForWriter(t *testing.T) {
	path := filepath.Join(t.TempDir(), "not-an-executable")
	if err := syscall.Mkfifo(path, 0600); err != nil {
		t.Fatal(err)
	}
	start := time.Now()
	file, err := openPinnedLabTool(context.Background(), LabToolSpec{Path: path, SHA256: strings.Repeat("0", 64)})
	if file != nil {
		file.Close()
	}
	if err == nil || time.Since(start) > time.Second {
		t.Fatal("non-regular tool blocked or was accepted", err)
	}
}
