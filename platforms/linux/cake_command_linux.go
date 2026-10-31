//go:build linux && !android

package linux

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"time"
)

const cakeCommandTimeout = 2 * time.Second
const cakeExecutableLimit = 64 * 1024 * 1024

var errCakeOutputLimit = errors.New("laboratory tool output limit exceeded")

func openPinnedLabTool(ctx context.Context, spec LabToolSpec) (*os.File, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if err := spec.Validate(); err != nil {
		return nil, err
	}
	canonical, err := filepath.EvalSymlinks(spec.Path)
	if err != nil {
		return nil, err
	}
	if canonical != spec.Path {
		return nil, fmt.Errorf("laboratory tool path contains a symlink")
	}
	file, err := os.OpenFile(spec.Path, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return nil, err
	}
	accepted := false
	defer func() {
		if !accepted {
			file.Close()
		}
	}()
	info, err := file.Stat()
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0111 == 0 || info.Size() < 4 || info.Size() > cakeExecutableLimit {
		return nil, fmt.Errorf("bounded executable ELF file required")
	}
	hash := sha256.New()
	buffer := make([]byte, 32*1024)
	total := 0
	for {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		n, err := file.Read(buffer)
		total += n
		if total > cakeExecutableLimit {
			return nil, fmt.Errorf("laboratory executable grew beyond size limit")
		}
		if n > 0 {
			hash.Write(buffer[:n])
		}
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
	}
	if hex.EncodeToString(hash.Sum(nil)) != spec.SHA256 {
		return nil, fmt.Errorf("laboratory tool SHA-256 changed")
	}
	var magic [4]byte
	if _, err := file.ReadAt(magic[:], 0); err != nil || string(magic[:]) != "\x7fELF" {
		return nil, fmt.Errorf("laboratory tool must be ELF, without shell interpreter")
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	accepted = true
	return file, nil
}

type cakeCommandBuffer struct {
	data      []byte
	limit     int
	truncated bool
	cancel    context.CancelCauseFunc
}

func (b *cakeCommandBuffer) Write(data []byte) (int, error) {
	remaining := b.limit - len(b.data)
	if len(data) > remaining {
		b.data = append(b.data, data[:remaining]...)
		b.truncated = true
		b.cancel(errCakeOutputLimit)
		return remaining, errCakeOutputLimit
	}
	b.data = append(b.data, data...)
	return len(data), nil
}

// runCakeTool is private and is called only with fixed ip/tc argument lists.
// The child stays in the worker's process group for the independent supervisor.
// Only the pinned executable FD is inherited; no control/namespace FD is passed.
func runCakeTool(parent context.Context, spec LabToolSpec, args []string, stdoutLimit int) (call LabToolCall, err error) {
	start := time.Now()
	call = LabToolCall{Path: spec.Path, SHA256: spec.SHA256, Arguments: append([]string(nil), args...), StartedAt: start.UTC()}
	defer func() {
		call.Duration = time.Since(start)
		if err != nil {
			call.Error = err.Error()
		}
	}()
	ctx, timeout := context.WithTimeout(parent, cakeCommandTimeout)
	defer timeout()
	ctx, cancel := context.WithCancelCause(ctx)
	defer cancel(nil)
	file, err := openPinnedLabTool(ctx, spec)
	if err != nil {
		return call, err
	}
	defer file.Close()
	// Execute the verified open object, rather than resolving its path again.
	command := exec.CommandContext(ctx, "/proc/self/fd/3", args...)
	command.Args[0] = spec.Path
	command.ExtraFiles = []*os.File{file}
	command.Env = []string{"LANG=C", "LC_ALL=C"}
	command.WaitDelay = 100 * time.Millisecond
	stdout := &cakeCommandBuffer{limit: stdoutLimit, cancel: cancel}
	stderr := &cakeCommandBuffer{limit: cakeOutputLimit, cancel: cancel}
	command.Stdout, command.Stderr = stdout, stderr
	if err = command.Start(); err == nil {
		call.PID = command.Process.Pid
		err = command.Wait()
		if command.ProcessState != nil {
			code := command.ProcessState.ExitCode()
			call.ExitCode = &code
		}
	}
	call.Stdout, call.Stderr = stdout.data, stderr.data
	call.StdoutTruncated, call.StderrTruncated = stdout.truncated, stderr.truncated
	if cause := context.Cause(ctx); cause != nil {
		err = errors.Join(cause, err)
	}
	return call, err
}
