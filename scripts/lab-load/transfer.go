package main

import (
	"context"
	"io"
	"net"
	"runtime"
	"time"
)

const blockBytes = 16 * 1024

// These byte counts describe application writes, not TCP/IP or link overhead.
type sendReport struct {
	SchemaVersion           int       `json:"schema_version"`
	Method                  string    `json:"method"`
	OS                      string    `json:"os"`
	Architecture            string    `json:"architecture"`
	GoVersion               string    `json:"go_version"`
	Target                  string    `json:"target"`
	RequestedBytes          int64     `json:"requested_bytes"`
	WrittenBytes            int64     `json:"written_bytes"`
	RequestedBytesPerSecond int64     `json:"requested_bytes_per_second"`
	BlockBytes              int       `json:"block_bytes"`
	TimeoutMS               float64   `json:"timeout_ms"`
	StartedAt               time.Time `json:"started_at"`
	FirstWriteAt            time.Time `json:"first_write_at"`
	LastWriteAt             time.Time `json:"last_write_at"`
	FinishedAt              time.Time `json:"finished_at"`
	ElapsedMS               float64   `json:"elapsed_ms"`
	AverageBytesPerSecond   float64   `json:"average_bytes_per_second"`
}

// scheduledDuration rounds up the minimum pacing duration for a byte budget.
// Inputs are validated and small enough to keep this integer arithmetic bounded.
func scheduledDuration(bytes, rate int64) time.Duration {
	return time.Duration((bytes*int64(time.Second) + rate - 1) / rate)
}

func waitForPace(ctx context.Context, started time.Time, written, rate int64) error {
	delay := time.Until(started.Add(scheduledDuration(written, rate)))
	if delay <= 0 {
		return ctx.Err()
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return ctx.Err()
	}
}

func closeOnCancel(ctx context.Context, connection net.Conn) (func() bool, error) {
	if deadline, ok := ctx.Deadline(); ok {
		if err := connection.SetDeadline(deadline); err != nil {
			return nil, err
		}
	}
	return context.AfterFunc(ctx, func() { connection.Close() }), nil
}

func send(ctx context.Context, o options, dial func(context.Context, string, string) (net.Conn, error), onFirstWrite func() error) (sendReport, error) {
	report := sendReport{SchemaVersion: 1, Method: "synthetic_tcp_send", OS: runtime.GOOS,
		Architecture: runtime.GOARCH, GoVersion: runtime.Version(), Target: o.address,
		RequestedBytes: o.bytes, RequestedBytesPerSecond: o.rate, BlockBytes: blockBytes,
		TimeoutMS: float64(o.duration) / float64(time.Millisecond), StartedAt: time.Now().UTC()}
	if err := o.validate(true); err != nil {
		return report, err
	}
	if err := ctx.Err(); err != nil {
		return report, err
	}
	started := time.Now()
	report.StartedAt = started.UTC()
	connection, err := dial(ctx, "tcp4", o.address)
	if err != nil {
		return report, err
	}
	defer connection.Close()
	stop, err := closeOnCancel(ctx, connection)
	if err != nil {
		return report, err
	}
	defer stop()
	paceStarted := time.Now()
	var zeros [blockBytes]byte
	for report.WrittenBytes < o.bytes {
		if err := ctx.Err(); err != nil {
			return report, err
		}
		size := min(int64(len(zeros)), o.bytes-report.WrittenBytes)
		n, err := connection.Write(zeros[:int(size)])
		if n < 0 || int64(n) > size {
			return report, io.ErrShortWrite
		}
		report.WrittenBytes += int64(n)
		if n > 0 {
			report.LastWriteAt = time.Now().UTC()
			if report.FirstWriteAt.IsZero() {
				report.FirstWriteAt = report.LastWriteAt
				if onFirstWrite != nil {
					if err := onFirstWrite(); err != nil {
						return report, err
					}
				}
			}
		}
		if err != nil {
			return report, err
		}
		if n == 0 {
			return report, io.ErrShortWrite
		}
		// Include a final wait after the last block; the first burst is <= 16 KiB.
		if err := waitForPace(ctx, paceStarted, report.WrittenBytes, o.rate); err != nil {
			return report, err
		}
	}
	if err := connection.Close(); err != nil {
		return report, err
	}
	finished := time.Now()
	report.FinishedAt = finished.UTC()
	report.ElapsedMS = float64(finished.Sub(started)) / float64(time.Millisecond)
	report.AverageBytesPerSecond = float64(report.WrittenBytes) / finished.Sub(started).Seconds()
	return report, nil
}
