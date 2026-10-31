//go:build linux && !android

package labcontrol

import (
	"context"
	"errors"
	"fmt"
	"os"
	"syscall"
	"time"

	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

// Descriptor numbers belong to the internal launcher, never to the JSON.
const (
	ControlFD           = 3
	EventsFD            = 4
	TargetNamespaceFD   = 5
	OriginalNamespaceFD = 6
)

// WorkerTransport owns four inherited descriptors. A single worker uses it
// sequentially; Close must not run concurrently with a protocol operation.
type WorkerTransport struct {
	control, events  *os.File
	target, original *os.File
	written          int
	failed           error
}

// OpenInheritedTransport consumes FDs 3..6, including on failure. Pipes must be
// FIFO descriptors in the correct direction. Kernel namespace types are checked
// immediately; identity and current binding are checked by Session.BindNamespace.
// Call this before setting up pollable I/O in a dedicated worker whose launcher
// owns these slots; the regular journal FD may be checked first. Never use this
// as a probe in another application's running process.
func OpenInheritedTransport() (_ *WorkerTransport, result error) {
	t := &WorkerTransport{}
	files := []**os.File{&t.control, &t.events, &t.target, &t.original}
	defer func() {
		if result == nil {
			return
		}
		// Consume the original slots even if validation failed before wrapping.
		for i, slot := range files {
			if *slot != nil {
				_ = (*slot).Close()
			} else {
				_ = syscall.Close(ControlFD + i)
			}
		}
	}()
	var stats [4]syscall.Stat_t
	// Inspect all raw slots before registering any pipe with Go's poller. A
	// missing inherited FD must not be replaced by a newly allocated poller FD.
	for i := range files {
		fd := ControlFD + i
		if err := syscall.Fstat(fd, &stats[i]); err != nil {
			return nil, err
		}
		if i < 2 {
			flags, _, errno := syscall.Syscall(syscall.SYS_FCNTL, uintptr(fd), syscall.F_GETFL, 0)
			direction := syscall.O_RDONLY
			if i == 1 {
				direction = syscall.O_WRONLY
			}
			if errno != 0 || stats[i].Mode&syscall.S_IFMT != syscall.S_IFIFO || int(flags)&syscall.O_ACCMODE != direction {
				return nil, fmt.Errorf("invalid inherited worker pipe %d", fd)
			}
		}
		syscall.CloseOnExec(fd)
		flags, _, errno := syscall.Syscall(syscall.SYS_FCNTL, uintptr(fd), syscall.F_GETFD, 0)
		if errno != 0 || flags&syscall.FD_CLOEXEC == 0 {
			return nil, fmt.Errorf("worker descriptor is not close-on-exec")
		}
	}
	if stats[0].Dev == stats[1].Dev && stats[0].Ino == stats[1].Ino {
		return nil, fmt.Errorf("worker requires two distinct pipes")
	}
	t.target = os.NewFile(TargetNamespaceFD, "inherited-target-namespace")
	t.original = os.NewFile(OriginalNamespaceFD, "inherited-original-namespace")
	for _, file := range []*os.File{t.target, t.original} {
		if _, err := linux.InspectNetworkNamespaceDescriptor(file); err != nil {
			return nil, err
		}
	}
	for i := 0; i < 2; i++ {
		fd := ControlFD + i
		// Register inherited pipes as nonblocking so deadlines are supported.
		if err := syscall.SetNonblock(fd, true); err != nil {
			return nil, err
		}
		*files[i] = os.NewFile(uintptr(fd), "inherited-worker-pipe")
		if *files[i] == nil {
			return nil, fmt.Errorf("inherited pipe is unavailable")
		}
	}
	if err := t.control.SetReadDeadline(time.Time{}); err != nil {
		return nil, err
	}
	if err := t.events.SetWriteDeadline(time.Time{}); err != nil {
		return nil, err
	}
	return t, nil
}

func (t *WorkerTransport) Close() error {
	var result error
	for _, f := range []*os.File{t.control, t.events, t.target, t.original} {
		if f != nil {
			result = errors.Join(result, f.Close())
		}
	}
	t.control, t.events, t.target, t.original = nil, nil, nil, nil
	return result
}

// withDeadline interrupts both blocked reads and blocked writes on cancellation.
// It joins the cancellation callback before returning, so a late callback can
// never alter the deadline of the next operation. Errors poison this transport.
func (t *WorkerTransport) withDeadline(ctx context.Context, file *os.File, deadline time.Time, write bool, operation func() error) error {
	if t.failed != nil {
		return t.failed
	}
	if file == nil {
		t.failed = fmt.Errorf("worker transport is closed")
		return t.failed
	}
	if err := ctx.Err(); err != nil {
		t.failed = err
		return err
	}
	if deadline.IsZero() {
		t.failed = fmt.Errorf("worker transport requires a deadline")
		return t.failed
	}
	if limit, ok := ctx.Deadline(); ok && limit.Before(deadline) {
		deadline = limit
	}
	set := file.SetReadDeadline
	if write {
		set = file.SetWriteDeadline
	}
	if err := set(deadline); err != nil {
		t.failed = err
		return err
	}
	done := make(chan struct{})
	stop := context.AfterFunc(ctx, func() { defer close(done); _ = set(time.Now()) })
	err := operation()
	if !stop() {
		<-done
	}
	if ctx.Err() != nil {
		err = ctx.Err()
	}
	if err == nil && !time.Now().Before(deadline) {
		err = os.ErrDeadlineExceeded
	}
	if err != nil {
		t.failed = err
	}
	return err
}

func (t *WorkerTransport) ReadRequest(ctx context.Context, deadline time.Time) (Request, error) {
	var request Request
	err := t.withDeadline(ctx, t.control, deadline, false, func() error {
		var err error
		request, err = ReadRequest(t.control)
		return err
	})
	return request, err
}

func (t *WorkerTransport) receive(ctx context.Context, session *Session) error {
	if err := session.Check(); err != nil {
		return err
	}
	err := t.withDeadline(ctx, t.control, session.boundary, false, func() error { return session.Receive(t.control) })
	if err != nil {
		return session.Abort(err)
	}
	return nil
}

func (t *WorkerTransport) send(ctx context.Context, session *Session, frame []byte) error {
	if err := session.Check(); err != nil {
		return err
	}
	if len(frame) > MaxEventBytes+4 || len(frame) > MaxOutputBytes-t.written {
		return session.Abort(fmt.Errorf("worker output budget exceeded"))
	}
	err := t.withDeadline(ctx, t.events, session.boundary, true, func() error { return writeAll(t.events, frame) })
	if err != nil {
		return session.Abort(err)
	}
	t.written += len(frame)
	return nil
}
