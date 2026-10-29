package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"math"
	"net"
	"strconv"
	"strings"
	"testing"
	"time"
)

type readerFunc func([]byte) (int, error)

func (f readerFunc) Read(data []byte) (int, error) { return f(data) }

func TestReceiptTimesIncludeEOFAfterLastBytes(t *testing.T) {
	base := time.Now()
	times := []time.Time{base, base.Add(time.Second), base.Add(3 * time.Second)}
	steps := 0
	reader := readerFunc(func(data []byte) (int, error) {
		if steps < 2 {
			return 2, nil
		}
		return 0, io.EOF
	})
	report, err := readReceipt(context.Background(), reader, 4, func() time.Time {
		at := times[steps]
		steps++
		return at
	})
	if err != nil || report.ReceivedBytes != 4 || report.ReceiveElapsedMS != 3000 ||
		!report.FirstReadAt.Equal(base) || !report.LastReadAt.Equal(times[1]) || !report.FinishedAt.Equal(times[2]) ||
		report.AverageBytesPerSecond == nil || *report.AverageBytesPerSecond != 4.0/3.0 {
		t.Fatalf("incorrect receipt window/rate: %+v err=%v", report, err)
	}
}

func TestSingleReadWithEOFHasExplicitlyUnavailableZeroDurationRate(t *testing.T) {
	at := time.Now()
	report, err := readReceipt(context.Background(), readerFunc(func([]byte) (int, error) { return 4, io.EOF }),
		4, func() time.Time { return at })
	if err != nil || report.ReceivedBytes != 4 || report.ReceiveElapsedMS != 0 || report.AverageBytesPerSecond != nil {
		t.Fatalf("zero-duration receipt: %+v %v", report, err)
	}
	raw, err := json.Marshal(report)
	if err != nil || !bytes.Contains(raw, []byte(`"average_bytes_per_second":null`)) {
		t.Fatalf("unavailable rate is not explicit: %s %v", raw, err)
	}
}

func TestReceiptRejectsPartialReadErrorsAndNoProgress(t *testing.T) {
	want := errors.New("read failed")
	report, err := readReceipt(context.Background(), readerFunc(func([]byte) (int, error) { return 2, want }), 4, time.Now)
	if !errors.Is(err, want) || report.ReceivedBytes != 2 || report.AverageBytesPerSecond != nil {
		t.Fatalf("partial error ignored: %+v %v", report, err)
	}
	_, err = readReceipt(context.Background(), readerFunc(func([]byte) (int, error) { return 0, nil }), 4, time.Now)
	if !errors.Is(err, io.ErrNoProgress) {
		t.Fatalf("no progress: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	report, err = readReceipt(ctx, readerFunc(func([]byte) (int, error) { cancel(); return 2, nil }), 4, time.Now)
	if !errors.Is(err, context.Canceled) || report.ReceivedBytes != 2 {
		t.Fatalf("cancellation lost: %+v %v", report, err)
	}
}

func TestReceiptNeverReadsBeyondExpectedPlusOne(t *testing.T) {
	var total int64
	reader := readerFunc(func(data []byte) (int, error) {
		if len(data) > blockBytes {
			t.Fatal("read buffer exceeded its limit")
		}
		total += int64(len(data))
		return len(data), nil
	})
	expected := int64(blockBytes + 7)
	report, err := readReceipt(context.Background(), reader, expected, time.Now)
	if err == nil || total != expected+1 || report.ReceivedBytes != total {
		t.Fatalf("excessive read budget: total=%d report=%+v err=%v", total, report, err)
	}
}

func assertReceiptJSON(t *testing.T, output, address string, expected int64) receiveReport {
	t.Helper()
	line, raw, ok := strings.Cut(output, "\n")
	if !ok || line != "READY "+address {
		t.Fatalf("missing readiness: %q", output)
	}
	var report receiveReport
	if err := json.Unmarshal([]byte(raw), &report); err != nil {
		t.Fatal(err)
	}
	if report.SchemaVersion != 1 || report.Method != "synthetic_tcp_receive" || report.Listen != address ||
		report.RequestedBytes != expected || report.ReceivedBytes != expected || report.BlockBytes != blockBytes ||
		report.FirstReadAt.Before(report.StartedAt) || report.LastReadAt.Before(report.FirstReadAt) ||
		report.FinishedAt.Before(report.LastReadAt) || report.ElapsedMS < report.ReceiveElapsedMS ||
		report.ReceiveElapsedMS <= 0 || report.AverageBytesPerSecond == nil {
		t.Fatalf("invalid receipt metadata: %+v", report)
	}
	want := float64(expected) / (report.ReceiveElapsedMS / 1000)
	if math.Abs(*report.AverageBytesPerSecond-want) > want*1e-12 {
		t.Fatalf("rate does not use receive window: %+v", report)
	}
	return report
}

func TestReceiverJSONIsOptInAndOnlyFollowsExactReceipt(t *testing.T) {
	for _, enabled := range []bool{false, true} {
		for _, size := range []int{256, 257, 258} {
			t.Run(strconv.FormatBool(enabled)+"/"+strconv.Itoa(size), func(t *testing.T) {
				source, sink := net.Pipe()
				defer source.Close()
				defer sink.Close()
				go func() { source.Write(make([]byte, size)); source.Close() }()
				args := []string{"receive", "--listen", "10.203.0.6:46002", "--bytes", "257", "--duration", "1s"}
				if enabled {
					args = append(args, "--json")
				}
				var stdout, stderr bytes.Buffer
				ctx, cancel := context.WithTimeout(context.Background(), time.Second)
				defer cancel()
				listener := newListener(sink)
				code := run(ctx, args, &stdout, &stderr, network{listen: func(context.Context, string, string) (net.Listener, error) { return listener, nil }})
				if size == 257 && enabled {
					if code != 0 {
						t.Fatalf("code=%d %s", code, &stderr)
					}
					assertReceiptJSON(t, stdout.String(), "10.203.0.6:46002", 257)
				} else if stdout.String() != "READY 10.203.0.6:46002\n" || (code == 0) != (size == 257) {
					t.Fatalf("unexpected output/code: %q code=%d", &stdout, code)
				}
			})
		}
	}
}
