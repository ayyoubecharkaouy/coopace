package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"runtime"
	"time"
)

// Receipt timing excludes waiting for the first progressing Read, includes
// waiting for EOF, and measures the application rather than a wire rate.
type receiveReport struct {
	SchemaVersion         int       `json:"schema_version"`
	Method                string    `json:"method"`
	OS                    string    `json:"os"`
	Architecture          string    `json:"architecture"`
	GoVersion             string    `json:"go_version"`
	Listen                string    `json:"listen"`
	RequestedBytes        int64     `json:"requested_bytes"`
	ReceivedBytes         int64     `json:"received_bytes"`
	BlockBytes            int       `json:"block_bytes"`
	TimeoutMS             float64   `json:"timeout_ms"`
	StartedAt             time.Time `json:"started_at"`
	FirstReadAt           time.Time `json:"first_read_at"`
	LastReadAt            time.Time `json:"last_read_at"`
	FinishedAt            time.Time `json:"finished_at"`
	ElapsedMS             float64   `json:"elapsed_ms"`
	ReceiveElapsedMS      float64   `json:"receive_elapsed_ms"`
	AverageBytesPerSecond *float64  `json:"average_bytes_per_second"`
}

// readReceipt discards at most expected+1 bytes. The injected clock supports
// deterministic tests; production uses time.Now with its monotonic component.
func readReceipt(ctx context.Context, reader io.Reader, expected int64, now func() time.Time) (receiveReport, error) {
	var report receiveReport
	var first time.Time
	var buffer [blockBytes]byte
	emptyReads := 0
	for {
		if err := ctx.Err(); err != nil {
			return report, err
		}
		size := min(int64(len(buffer)), expected+1-report.ReceivedBytes)
		n, err := reader.Read(buffer[:int(size)])
		at := now()
		if n < 0 || int64(n) > size {
			return report, fmt.Errorf("comptage de lecture invalide : %d", n)
		}
		if n > 0 {
			emptyReads = 0
			report.ReceivedBytes += int64(n)
			report.LastReadAt = at.UTC()
			if first.IsZero() {
				first = at
				report.FirstReadAt = at.UTC()
			}
		} else if err == nil {
			emptyReads++
			if emptyReads >= 100 {
				return report, io.ErrNoProgress
			}
		}
		if report.ReceivedBytes > expected {
			return report, fmt.Errorf("volume reçu %d, attendu %d", report.ReceivedBytes, expected)
		}
		if err == io.EOF {
			if err := ctx.Err(); err != nil {
				return report, err
			}
			if report.ReceivedBytes != expected {
				return report, fmt.Errorf("volume reçu %d, attendu %d", report.ReceivedBytes, expected)
			}
			duration := at.Sub(first)
			if duration < 0 {
				return report, fmt.Errorf("durée de réception négative")
			}
			report.FinishedAt = at.UTC()
			report.ReceiveElapsedMS = float64(duration) / float64(time.Millisecond)
			if duration > 0 {
				rate := float64(report.ReceivedBytes) / duration.Seconds()
				report.AverageBytesPerSecond = &rate
			}
			return report, nil
		}
		if err != nil {
			return report, err
		}
	}
}

func receive(ctx context.Context, o options, listen func(context.Context, string, string) (net.Listener, error), ready func(string) error) (receiveReport, error) {
	report := receiveReport{SchemaVersion: 1, Method: "synthetic_tcp_receive", OS: runtime.GOOS,
		Architecture: runtime.GOARCH, GoVersion: runtime.Version(), Listen: o.address,
		RequestedBytes: o.bytes, BlockBytes: blockBytes, TimeoutMS: float64(o.duration) / float64(time.Millisecond)}
	if err := o.validate(false); err != nil {
		return report, err
	}
	if err := ctx.Err(); err != nil {
		return report, err
	}
	started := time.Now()
	report.StartedAt = started.UTC()
	listener, err := listen(ctx, "tcp4", o.address)
	if err != nil {
		return report, err
	}
	defer listener.Close()
	stopListener := context.AfterFunc(ctx, func() { listener.Close() })
	defer stopListener()
	if err := ready(listener.Addr().String()); err != nil {
		return report, err
	}
	connection, err := listener.Accept()
	if err != nil {
		return report, err
	}
	defer connection.Close()
	listener.Close()
	stop, err := closeOnCancel(ctx, connection)
	if err != nil {
		return report, err
	}
	defer stop()
	var finished time.Time
	receipt, err := readReceipt(ctx, connection, o.bytes, func() time.Time {
		finished = time.Now()
		return finished
	})
	report.ReceivedBytes = receipt.ReceivedBytes
	if err != nil {
		return report, err
	}
	report.FirstReadAt, report.LastReadAt = receipt.FirstReadAt, receipt.LastReadAt
	report.FinishedAt = receipt.FinishedAt
	report.ReceiveElapsedMS = receipt.ReceiveElapsedMS
	report.AverageBytesPerSecond = receipt.AverageBytesPerSecond
	report.ElapsedMS = float64(finished.Sub(started)) / float64(time.Millisecond)
	return report, nil
}
