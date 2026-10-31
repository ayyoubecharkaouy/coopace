//go:build linux && !android

package labcontrol

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

func TestTransportInterruptsPartialReadsAndBlockedWrites(t *testing.T) {
	for _, mode := range []string{"no_prefix", "partial_prefix", "partial_body", "cancel", "blocked_write", "cancel_write"} {
		t.Run(mode, func(t *testing.T) {
			reader, writer, err := os.Pipe()
			if err != nil {
				t.Fatal(err)
			}
			defer reader.Close()
			defer writer.Close()
			transport := &WorkerTransport{}
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			deadline := time.Now().Add(80 * time.Millisecond)
			var operation func() error
			file := reader
			write := false
			switch mode {
			case "partial_prefix":
				writer.Write([]byte{0, 0})
			case "partial_body":
				writer.Write([]byte{0, 0, 0, 20, '{'})
			case "cancel":
				deadline = time.Now().Add(5 * time.Second)
			case "blocked_write", "cancel_write":
				file, write = writer, true
				if mode == "cancel_write" {
					deadline = time.Now().Add(5 * time.Second)
				}
			}
			operation = func() error {
				if mode == "cancel" || mode == "cancel_write" {
					cancel()
				}
				if write {
					return writeAll(writer, bytes.Repeat([]byte("x"), 1024*1024))
				}
				_, err := ReadRequest(reader)
				return err
			}
			start := time.Now()
			err = transport.withDeadline(ctx, file, deadline, write, operation)
			if mode == "cancel" || mode == "cancel_write" {
				if !errors.Is(err, context.Canceled) {
					t.Fatal(err)
				}
			} else if !errors.Is(err, os.ErrDeadlineExceeded) {
				t.Fatalf("I/O did not expire: %v", err)
			}
			if time.Since(start) > 2*time.Second {
				t.Fatal("blocked operation not interrupted")
			}
			// A partially consumed or written frame cannot be retried.
			called := false
			if e := transport.withDeadline(context.Background(), file, time.Now().Add(time.Second), write, func() error { called = true; return nil }); e == nil || called {
				t.Fatal("failed transport resumed")
			}
		})
	}
}

func TestTransportBoundsOutputAndPropagatesClosedPeer(t *testing.T) {
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	defer r.Close()
	defer w.Close()
	s, _, _ := readySession(t)
	transport := &WorkerTransport{events: w, written: MaxOutputBytes - 3}
	if err := transport.send(context.Background(), s, []byte("four")); err == nil || s.Phase() != Failed {
		t.Fatal("output budget exceeded")
	}
	s, _, _ = readySession(t)
	transport = &WorkerTransport{events: w}
	s.boundary = time.Now().Add(time.Second)
	r.Close()
	if err := transport.send(context.Background(), s, []byte("x")); !errors.Is(err, syscall.EPIPE) {
		t.Fatal("closed peer ignored")
	}
}

type workerProcess struct {
	command         *exec.Cmd
	control, events *os.File
	stderr          bytes.Buffer
	calls           string
	identity        linux.NetworkNamespaceIdentity
	waited          bool
}

func startWorkerProcess(t *testing.T, mode string) *workerProcess {
	t.Helper()
	if runtime.GOARCH != "amd64" {
		t.Skip("inherited namespace bootstrap currently supports Linux amd64")
	}
	controlR, controlW, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	eventsR, eventsW, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	target, err := os.Open("/proc/thread-self/ns/net")
	if err != nil {
		t.Fatal(err)
	}
	original, err := os.Open("/proc/thread-self/ns/net")
	if err != nil {
		t.Fatal(err)
	}
	info, _ := target.Stat()
	stat := info.Sys().(*syscall.Stat_t)
	path, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	h := &workerProcess{control: controlW, events: eventsR, calls: filepath.Join(t.TempDir(), "tools"), identity: linux.NetworkNamespaceIdentity{Device: uint64(stat.Dev), Inode: uint64(stat.Ino)}}
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	h.command = exec.CommandContext(ctx, path, "-test.run=^TestTransportProcessHelper$")
	h.command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	h.command.Cancel = func() error { return syscall.Kill(-h.command.Process.Pid, syscall.SIGKILL) }
	h.command.Stderr = &h.stderr
	h.command.ExtraFiles = []*os.File{controlR, eventsW, target, original}
	h.command.Env = append(os.Environ(), "COOPACE_LAB_TRANSPORT_HELPER="+mode, "COOPACE_LAB_TOOL_CALLS="+h.calls, "GORACE=atexit_sleep_ms=0")
	if mode == "wrong_direction" {
		h.command.ExtraFiles[0] = controlW
	}
	if mode == "ordinary_pipe" {
		h.command.ExtraFiles[0] = target
	}
	if mode == "missing_namespace" {
		h.command.ExtraFiles[3] = nil
	}
	if err := h.command.Start(); err != nil {
		cancel()
		t.Fatal(err)
	}
	controlR.Close()
	eventsW.Close()
	target.Close()
	original.Close()
	t.Cleanup(func() {
		if !h.waited {
			// Signal the owned group before reaping its leader. Never signal a
			// PID/group number after Wait has released the leader's identity.
			_ = syscall.Kill(-h.command.Process.Pid, syscall.SIGKILL)
			_ = h.command.Wait()
		}
		cancel()
		h.control.Close()
		h.events.Close()
	})
	return h
}

func (h *workerProcess) request(t *testing.T, session string) {
	t.Helper()
	value := map[string]any{"schema_version": 1, "kind": "lab_cake_worker_request", "session_id": session, "purpose": "cake_down_control", "reference": "cake-ipv4-lab-4mbit-v1", "namespace_identity": map[string]uint64{"device": h.identity.Device, "inode": h.identity.Inode}}
	data, _ := json.Marshal(value)
	h.control.SetWriteDeadline(time.Now().Add(3 * time.Second))
	if err := writeAll(h.control, frame(string(data))); err != nil {
		t.Fatal(err)
	}
}

func (h *workerProcess) send(t *testing.T, action string) {
	t.Helper()
	h.control.SetWriteDeadline(time.Now().Add(3 * time.Second))
	if err := writeAll(h.control, frame(commandJSON(action, "abcd1234"))); err != nil {
		t.Fatal(err)
	}
}

func (h *workerProcess) event(t *testing.T, name string) workerEvent {
	t.Helper()
	h.events.SetReadDeadline(time.Now().Add(3 * time.Second))
	var prefix [4]byte
	if _, err := io.ReadFull(h.events, prefix[:]); err != nil {
		t.Fatal(err)
	}
	size := binary.BigEndian.Uint32(prefix[:])
	if size == 0 || size > MaxEventBytes {
		t.Fatal("invalid event length")
	}
	data := make([]byte, size)
	if _, err := io.ReadFull(h.events, data); err != nil {
		t.Fatal(err)
	}
	var event workerEvent
	if err := json.Unmarshal(data, &event); err != nil {
		t.Fatal(err)
	}
	if event.Event != name || event.Kind != "lab_cake_worker_event" || event.Session != "abcd1234" {
		t.Fatalf("unexpected event %+v", event)
	}
	return event
}

func (h *workerProcess) wait() error       { err := h.command.Wait(); h.waited = true; return err }
func (h *workerProcess) toolCalls() string { data, _ := os.ReadFile(h.calls); return string(data) }

func TestInheritedWorkerProcessSequenceClosesToolDescriptorsAndRechecksBeforeExit(t *testing.T) {
	h := startWorkerProcess(t, "flow")
	h.request(t, "abcd1234")
	h.event(t, "ready")
	if calls := h.toolCalls(); calls != "initial\n" {
		t.Fatalf("apply happened before instruction: %q", calls)
	}
	h.send(t, "apply")
	event := h.event(t, "applied")
	if _, err := linux.ParseCakeReading(event.Raw, event.Producer); err != nil {
		t.Fatal(err)
	}
	h.send(t, "finish")
	if err := h.wait(); err != nil {
		t.Fatalf("worker failed: %v %s", err, h.stderr.String())
	}
	if calls := h.toolCalls(); calls != "initial\napply\nfinal\n" {
		t.Fatalf("incorrect tool sequence: %q", calls)
	}
	h.events.SetReadDeadline(time.Now().Add(time.Second))
	var last [1]byte
	if _, err := h.events.Read(last[:]); err != io.EOF {
		t.Fatalf("inherited pipe leaked: %v", err)
	}
}

func TestInheritedWorkerRejectsDescriptorsSessionsEOFAndRepeatedApply(t *testing.T) {
	for _, mode := range []string{"wrong_direction", "ordinary_pipe", "missing_namespace", "native_original", "native_backend", "wrong_session", "premature_finish", "eof", "duplicate_apply", "invalid_final"} {
		t.Run(mode, func(t *testing.T) {
			h := startWorkerProcess(t, mode)
			if mode == "wrong_direction" || mode == "ordinary_pipe" || mode == "missing_namespace" {
				if err := h.wait(); err == nil {
					t.Fatal("invalid inherited descriptors accepted")
				}
				if h.toolCalls() != "" {
					t.Fatal("tool ran before descriptor validation")
				}
				return
			}
			session := "abcd1234"
			if mode == "wrong_session" {
				session = "other123"
			}
			h.request(t, session)
			if mode == "native_original" || mode == "native_backend" || mode == "wrong_session" {
				if err := h.wait(); err == nil {
					t.Fatal("unbound context admitted")
				}
				if h.toolCalls() != "" {
					t.Fatal("tool ran before binding")
				}
				if mode == "native_backend" && !strings.Contains(h.stderr.String(), "original supervisor network namespace") {
					t.Fatal("native backend failed at the wrong boundary", h.stderr.String())
				}
				return
			}
			h.event(t, "ready")
			switch mode {
			case "eof":
				h.control.Close()
			case "premature_finish":
				h.send(t, "finish")
			default:
				h.send(t, "apply")
				h.event(t, "applied")
				if mode == "duplicate_apply" {
					h.send(t, "apply")
				} else {
					h.send(t, "finish")
				}
			}
			if err := h.wait(); err == nil {
				t.Fatal("invalid protocol accepted")
			}
			if strings.Count(h.toolCalls(), "apply\n") > 1 {
				t.Fatal("apply retried")
			}
		})
	}
}

func TestInheritedWorkerStopsBlockedInitializationAndForcedTerminationClosesChannels(t *testing.T) {
	h := startWorkerProcess(t, "short_context")
	start := time.Now()
	if err := h.wait(); err == nil || time.Since(start) > 2*time.Second {
		t.Fatalf("blocked initialization ignored cancellation: %v", err)
	}
	if h.toolCalls() != "" {
		t.Fatal("uninitialized worker ran tool")
	}
	h = startWorkerProcess(t, "flow")
	h.request(t, "abcd1234")
	h.event(t, "ready")
	if err := syscall.Kill(-h.command.Process.Pid, syscall.SIGKILL); err != nil {
		t.Fatal(err)
	}
	if err := h.wait(); err == nil {
		t.Fatal("forced termination reported success")
	}
	h.events.SetReadDeadline(time.Now().Add(time.Second))
	var last [1]byte
	if _, err := h.events.Read(last[:]); err != io.EOF {
		t.Fatal("child descriptor retained after death", err)
	}
}

func TestInheritedWorkerCancellationReapsBlockedFakeTool(t *testing.T) {
	h := startWorkerProcess(t, "tool_wait")
	h.request(t, "abcd1234")
	h.event(t, "ready")
	h.send(t, "apply")
	if err := h.wait(); err == nil {
		t.Fatal("blocked tool returned success")
	}
	data, err := os.ReadFile(h.calls + ".pid")
	if err != nil {
		t.Fatal("fake tool never started", err, h.stderr.String())
	}
	pid, err := strconv.Atoi(string(data))
	if err != nil || pid <= 0 {
		t.Fatal("missing tool PID")
	}
	if _, err := os.Stat(fmt.Sprintf("/proc/%d", pid)); !os.IsNotExist(err) {
		t.Fatal("cancelled tool was not reaped", err)
	}
}

// The positive test driver simulates namespace acceptance and tool output. Only
// the inherited pipes, FDs, child execution and cancellation are actual OS work.
func TestTransportProcessHelper(t *testing.T) {
	mode := os.Getenv("COOPACE_LAB_TRANSPORT_HELPER")
	if mode == "" {
		return
	}
	started := time.Now()
	transport, err := OpenInheritedTransport()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if mode == "native_backend" {
		// Production assembly has no verifier injection or PATH/tool fallback.
		tools := nativeTools{ip: linux.LabToolSpec{Path: "/missing/ip", SHA256: strings.Repeat("0", 64)}, tc: linux.LabToolSpec{Path: "/missing/tc", SHA256: strings.Repeat("0", 64)}}
		evidence, err := runNativeWorker(context.Background(), transport, "abcd1234", started, tools)
		if err == nil || len(evidence.Calls) != 0 {
			fmt.Fprintln(os.Stderr, "invalid native binding admitted")
			os.Exit(2)
		}
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if syscall.Getpgrp() != os.Getpid() {
		fmt.Fprintln(os.Stderr, "worker not in its own group")
		os.Exit(2)
	}
	// Record identities, not numeric FD slots: Go may reuse closed slots in a
	// tool. A tool must inherit none of these actual objects.
	var forbidden []string
	for _, file := range []*os.File{transport.control, transport.events, transport.target, transport.original} {
		info, err := file.Stat()
		if err != nil {
			os.Exit(2)
		}
		stat := info.Sys().(*syscall.Stat_t)
		forbidden = append(forbidden, fmt.Sprintf("%d:%d", stat.Dev, stat.Ino))
	}
	tool := func(ctx context.Context, phase string) ([]byte, error) {
		path, _ := os.Executable()
		command := exec.CommandContext(ctx, path, "-test.run=^TestTransportToolHelper$", "--", phase)
		command.WaitDelay = 100 * time.Millisecond
		command.Env = append(os.Environ(), "COOPACE_LAB_TOOL=1", "COOPACE_LAB_FORBIDDEN_FDS="+strings.Join(forbidden, ","), "GORACE=atexit_sleep_ms=0")
		command.Stderr = os.Stderr
		return command.Output()
	}
	operations := workerOperations{
		initial: func(ctx context.Context) ([]byte, error) { return tool(ctx, "initial") },
		apply: func(ctx context.Context) ([]byte, linux.CakeProducerProfile, error) {
			phase := "apply"
			if mode == "tool_wait" {
				phase = "wait"
			}
			data, err := tool(ctx, phase)
			return data, linux.CakeIPRoute2V610, err
		},
		final: func(ctx context.Context) ([]byte, error) {
			if mode == "invalid_final" {
				return []byte("[]"), nil
			}
			return tool(ctx, "final")
		},
	}
	if mode != "native_original" {
		operations.verify = func(expected linux.NetworkNamespaceIdentity, target, original *os.File) error {
			for _, file := range []*os.File{target, original} {
				info, err := file.Stat()
				if err != nil {
					return err
				}
				stat := info.Sys().(*syscall.Stat_t)
				if uint64(stat.Dev) != expected.Device || uint64(stat.Ino) != expected.Inode {
					return fmt.Errorf("inherited identity changed")
				}
			}
			return nil // simulated distinction from the supervisor namespace
		}
	}
	ctx := context.Background()
	var cancel context.CancelFunc
	if mode == "short_context" {
		ctx, cancel = context.WithTimeout(ctx, 100*time.Millisecond)
		defer cancel()
	}
	if mode == "tool_wait" {
		ctx, cancel = context.WithTimeout(ctx, time.Second)
		defer cancel()
	}
	if err := runWorker(ctx, transport, "abcd1234", started, operations); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	os.Exit(0)
}

func TestTransportToolHelper(t *testing.T) {
	if os.Getenv("COOPACE_LAB_TOOL") != "1" {
		return
	}
	forbidden := "," + os.Getenv("COOPACE_LAB_FORBIDDEN_FDS") + ","
	entries, err := os.ReadDir("/proc/self/fd")
	if err != nil {
		os.Exit(2)
	}
	for _, entry := range entries {
		fd, err := strconv.Atoi(entry.Name())
		if err != nil || fd < 3 {
			continue
		}
		var stat syscall.Stat_t
		if syscall.Fstat(fd, &stat) == nil && strings.Contains(forbidden, fmt.Sprintf(",%d:%d,", stat.Dev, stat.Ino)) {
			fmt.Fprintln(os.Stderr, "control descriptor leaked into tool")
			os.Exit(2)
		}
	}
	phase := os.Args[len(os.Args)-1]
	if phase != "initial" && phase != "apply" && phase != "final" && phase != "wait" {
		os.Exit(2)
	}
	file, err := os.OpenFile(os.Getenv("COOPACE_LAB_TOOL_CALLS"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		os.Exit(2)
	}
	_, err = file.WriteString(phase + "\n")
	file.Close()
	if err != nil {
		os.Exit(2)
	}
	if phase == "wait" {
		if err := os.WriteFile(os.Getenv("COOPACE_LAB_TOOL_CALLS")+".pid", []byte(strconv.Itoa(os.Getpid())), 0600); err != nil {
			os.Exit(2)
		}
		time.Sleep(10 * time.Second)
		os.Exit(2)
	}
	data := []byte("[]")
	if phase != "initial" {
		data, err = os.ReadFile("../../../../platforms/linux/testdata/cake/down.json")
		if err != nil {
			os.Exit(2)
		}
	}
	if err := writeAll(os.Stdout, data); err != nil {
		os.Exit(2)
	}
	os.Exit(0)
}
