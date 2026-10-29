package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"
)

type oneListener struct {
	incoming chan net.Conn
	closed   chan struct{}
	once     sync.Once
}

func newListener(connection net.Conn) *oneListener {
	l := &oneListener{incoming: make(chan net.Conn, 1), closed: make(chan struct{})}
	if connection != nil {
		l.incoming <- connection
	}
	return l
}

func (l *oneListener) Accept() (net.Conn, error) {
	select {
	case connection := <-l.incoming:
		return connection, nil
	case <-l.closed:
		return nil, net.ErrClosed
	}
}

func (l *oneListener) Close() error {
	l.once.Do(func() { close(l.closed) })
	return nil
}

func (l *oneListener) Addr() net.Addr {
	return &net.TCPAddr{IP: net.IPv4(10, 203, 0, 6), Port: 46002}
}

func testOptions() options {
	return options{address: "10.203.0.6:46002", bytes: 2*blockBytes + 17, rate: 4 * 1024 * 1024, duration: time.Second}
}

func TestCLISendsOnlyBoundedZerosAndReportsPacedWrites(t *testing.T) {
	source, sink := net.Pipe()
	defer source.Close()
	defer sink.Close()
	data := make(chan []byte, 1)
	go func() {
		payload, _ := io.ReadAll(sink)
		data <- payload
	}()
	o := testOptions()
	var stdout, stderr bytes.Buffer
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	code := run(ctx, []string{"send", "--target", o.address, "--bytes", strconv.FormatInt(o.bytes, 10), "--rate", strconv.FormatInt(o.rate, 10), "--duration", "1s"},
		&stdout, &stderr, network{dial: func(ctx context.Context, network, address string) (net.Conn, error) {
			if network != "tcp4" || address != o.address {
				t.Fatalf("unexpected destination: %s %s", network, address)
			}
			if _, ok := ctx.Deadline(); !ok {
				t.Fatal("missing transfer deadline")
			}
			return source, nil
		}})
	if code != 0 {
		t.Fatalf("code=%d stderr=%q", code, &stderr)
	}
	var report sendReport
	if err := json.Unmarshal(stdout.Bytes(), &report); err != nil {
		t.Fatal(err)
	}
	if report.SchemaVersion != 1 || report.Method != "synthetic_tcp_send" || report.WrittenBytes != o.bytes || report.RequestedBytes != o.bytes || report.RequestedBytesPerSecond != o.rate || report.BlockBytes != blockBytes || report.TimeoutMS != 1000 {
		t.Fatalf("wrong transfer metadata: %+v", report)
	}
	if report.ElapsedMS < float64(scheduledDuration(o.bytes, o.rate))/float64(time.Millisecond) || report.AverageBytesPerSecond > float64(o.rate) || report.FinishedAt.Before(report.StartedAt) {
		t.Fatalf("unpaced or inconsistent timing: %+v", report)
	}
	if report.FirstWriteAt.Before(report.StartedAt) || report.LastWriteAt.Before(report.FirstWriteAt) || report.LastWriteAt.After(report.FinishedAt) {
		t.Fatalf("invalid write activity window: %+v", report)
	}
	select {
	case payload := <-data:
		if len(payload) != int(o.bytes) || !bytes.Equal(payload, make([]byte, o.bytes)) {
			t.Fatal("payload was not the exact bounded synthetic volume")
		}
	case <-ctx.Done():
		t.Fatal("sender did not close the stream")
	}
}

func TestReceiverRequiresExactVolumeAndEOF(t *testing.T) {
	for _, size := range []int{256, 257, 258} {
		t.Run(strconv.Itoa(size), func(t *testing.T) {
			source, sink := net.Pipe()
			defer source.Close()
			defer sink.Close()
			listener := newListener(sink)
			defer listener.Close()
			ctx, cancel := context.WithTimeout(context.Background(), time.Second)
			defer cancel()
			go func() {
				source.Write(make([]byte, size))
				source.Close()
			}()
			o := testOptions()
			o.bytes = 257
			ready := ""
			received, err := receive(ctx, o,
				func(context.Context, string, string) (net.Listener, error) { return listener, nil },
				func(address string) error { ready = address; return nil })
			if received != int64(size) || (err == nil) != (size == 257) || ready != o.address {
				t.Fatalf("received=%d err=%v ready=%q", received, err, ready)
			}
			select {
			case <-listener.closed:
			default:
				t.Fatal("listening socket remained open")
			}
		})
	}
}

func TestAnnouncedStartPrecedesSuccessJSON(t *testing.T) {
	source, sink := net.Pipe()
	defer source.Close()
	defer sink.Close()
	go io.Copy(io.Discard, sink)
	var stdout, stderr bytes.Buffer
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	code := run(ctx, []string{"send", "--target", "10.203.0.6:46002", "--bytes", "32768", "--rate", "4194304", "--duration", "1s", "--announce-start"},
		&stdout, &stderr, network{dial: func(context.Context, string, string) (net.Conn, error) { return source, nil }})
	if code != 0 {
		t.Fatalf("code=%d stderr=%q", code, &stderr)
	}
	marker, raw, ok := strings.Cut(stdout.String(), "\n")
	if !ok || marker != "STARTED" {
		t.Fatalf("missing start announcement: %q", &stdout)
	}
	var report sendReport
	if err := json.Unmarshal([]byte(raw), &report); err != nil || report.WrittenBytes != 32768 || report.FirstWriteAt.IsZero() || !report.LastWriteAt.After(report.FirstWriteAt) {
		t.Fatalf("invalid announced report: %+v %v", report, err)
	}
}

func TestDeadlinesReleaseBlockedNetworkOperations(t *testing.T) {
	for _, operation := range []string{"accept", "read", "write", "pace"} {
		t.Run(operation, func(t *testing.T) {
			source, sink := net.Pipe()
			defer source.Close()
			defer sink.Close()
			ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
			defer cancel()
			o := testOptions()
			var stdout, stderr bytes.Buffer
			transport := network{}
			args := []string{"send", "--target", o.address}
			if operation == "accept" || operation == "read" {
				connection := net.Conn(sink)
				if operation == "accept" {
					connection = nil
				}
				listener := newListener(connection)
				defer listener.Close()
				transport.listen = func(context.Context, string, string) (net.Listener, error) { return listener, nil }
				args = []string{"receive", "--listen", o.address}
			} else {
				transport.dial = func(context.Context, string, string) (net.Conn, error) { return source, nil }
				if operation == "pace" {
					args = append(args, "--rate", "65536", "--bytes", "65536")
					go io.Copy(io.Discard, sink)
				}
			}
			done := make(chan int, 1)
			go func() { done <- run(ctx, args, &stdout, &stderr, transport) }()
			select {
			case code := <-done:
				if code != 1 {
					t.Fatalf("code=%d context=%v stderr=%q", code, ctx.Err(), &stderr)
				}
				// Socket deadlines can fire just before the context timer is scheduled.
				select {
				case <-ctx.Done():
				case <-time.After(time.Second):
					t.Fatal("operation failed before the configured deadline")
				}
				if operation == "write" || operation == "pace" {
					if stdout.Len() != 0 {
						t.Fatal("failed transfer emitted a success JSON report")
					}
				}
			case <-time.After(time.Second):
				t.Fatal("blocked operation survived its deadline")
			}
		})
	}
}

func TestCLIRejectsInvalidOptionsBeforeNetworkIO(t *testing.T) {
	for _, args := range [][]string{
		{"unknown"}, {"send"}, {"receive"},
		{"send", "--target", "example.org:46002"},
		{"send", "--target", "8.8.8.8:46002"},
		{"receive", "--listen", "0.0.0.0:46002"},
		{"receive", "--listen", "[::1]:46002"},
		{"receive", "--listen", "127.0.0.1:80"},
		{"send", "--target", "127.0.0.1:46002", "--bytes", "0"},
		{"receive", "--listen", "127.0.0.1:46002", "--bytes", "33554433"},
		{"send", "--target", "127.0.0.1:46002", "--rate", "65535"},
		{"send", "--target", "127.0.0.1:46002", "--rate", "4194305"},
		{"send", "--target", "127.0.0.1:46002", "--duration", "8s"},
		{"receive", "--listen", "127.0.0.1:46002", "--duration", "31s"},
		{"send", "--target", "127.0.0.1:46002", "extra"},
	} {
		var stdout, stderr bytes.Buffer
		transport := network{
			dial: func(context.Context, string, string) (net.Conn, error) {
				t.Fatal("invalid options dialed")
				return nil, nil
			},
			listen: func(context.Context, string, string) (net.Listener, error) {
				t.Fatal("invalid options listened")
				return nil, nil
			},
		}
		if code := run(context.Background(), args, &stdout, &stderr, transport); code != 2 || stdout.Len() != 0 {
			t.Fatalf("args=%v code=%d stdout=%q stderr=%q", args, code, &stdout, &stderr)
		}
	}
}

type shortConn struct {
	net.Conn
	maximum int
}

func (c shortConn) Write(data []byte) (int, error) {
	if c.maximum == 0 {
		return 0, nil
	}
	return c.Conn.Write(data[:min(len(data), c.maximum)])
}

func TestSenderHandlesShortWritesAndRejectsZeroProgress(t *testing.T) {
	for _, maximum := range []int{0, 7} {
		source, sink := net.Pipe()
		t.Cleanup(func() { source.Close(); sink.Close() })
		go io.Copy(io.Discard, sink)
		o := testOptions()
		o.bytes = 31
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		report, err := send(ctx, o, func(context.Context, string, string) (net.Conn, error) { return shortConn{source, maximum}, nil }, nil)
		if maximum == 0 {
			if !errors.Is(err, io.ErrShortWrite) || report.WrittenBytes != 0 {
				t.Fatalf("zero progress: %+v %v", report, err)
			}
		} else if err != nil || report.WrittenBytes != o.bytes {
			t.Fatalf("short writes: %+v %v", report, err)
		}
	}
}

func TestReadinessFailureClosesListener(t *testing.T) {
	listener := newListener(nil)
	want := errors.New("output unavailable")
	_, err := receive(context.Background(), testOptions(),
		func(context.Context, string, string) (net.Listener, error) { return listener, nil },
		func(string) error { return want })
	if !errors.Is(err, want) {
		t.Fatal(err)
	}
	select {
	case <-listener.closed:
	default:
		t.Fatal("readiness failure left the listener open")
	}
}

func TestLoopbackSyntheticTransfer(t *testing.T) {
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if errors.Is(err, syscall.EPERM) || errors.Is(err, syscall.EACCES) {
		t.Skipf("loopback socket denied in this environment: %v", err)
	}
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	o := testOptions()
	o.address = listener.Addr().String()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	done := make(chan error, 1)
	go func() {
		_, err := receive(ctx, o, func(context.Context, string, string) (net.Listener, error) { return listener, nil }, func(string) error { return nil })
		done <- err
	}()
	report, err := send(ctx, o, (&net.Dialer{}).DialContext, nil)
	if err != nil || report.WrittenBytes != o.bytes {
		t.Fatalf("send: %+v %v", report, err)
	}
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-ctx.Done():
		t.Fatal("receiver did not complete")
	}
}
