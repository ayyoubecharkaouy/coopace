package main

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"
)

type pipeListener struct {
	connections chan net.Conn
	closed      chan struct{}
	once        sync.Once
}

func newPipeListener() *pipeListener {
	return &pipeListener{connections: make(chan net.Conn, 2), closed: make(chan struct{})}
}

func (l *pipeListener) Accept() (net.Conn, error) {
	select {
	case conn := <-l.connections:
		return conn, nil
	case <-l.closed:
		return nil, net.ErrClosed
	}
}

func (l *pipeListener) Close() error {
	l.once.Do(func() { close(l.closed) })
	return nil
}

func (l *pipeListener) Addr() net.Addr {
	return &net.TCPAddr{IP: net.IPv4(10, 203, 0, 6), Port: 46001}
}

func testOptions() options {
	return options{address: "10.203.0.6:46001", connections: 2, duration: time.Second}
}

func TestServeClosesConnectionsWithoutPayloadAndStopsAtLimit(t *testing.T) {
	listener := newPipeListener()
	defer listener.Close()
	clients := make([]net.Conn, 0, 2)
	for range 2 {
		server, client := net.Pipe()
		defer server.Close()
		defer client.Close()
		client.SetReadDeadline(time.Now().Add(time.Second))
		listener.connections <- server
		clients = append(clients, client)
	}
	ready := ""
	err := serve(context.Background(), testOptions(),
		func(_ context.Context, network, address string) (net.Listener, error) {
			if network != "tcp4" || address != "10.203.0.6:46001" {
				t.Fatalf("unexpected binding: %s %s", network, address)
			}
			return listener, nil
		}, func(address string) error { ready = address; return nil })
	if err != nil || ready != "10.203.0.6:46001" {
		t.Fatalf("serve: ready=%q err=%v", ready, err)
	}
	for _, client := range clients {
		payload, err := io.ReadAll(client)
		if err != nil || len(payload) != 0 {
			t.Fatalf("expected immediate EOF without payload, got %q, %v", payload, err)
		}
	}
	select {
	case <-listener.closed:
	default:
		t.Fatal("listener remained open after the connection limit")
	}
}

func TestCancellationAndDeadlineReleaseAccept(t *testing.T) {
	for _, deadline := range []bool{false, true} {
		t.Run(map[bool]string{false: "cancel", true: "deadline"}[deadline], func(t *testing.T) {
			listener := newPipeListener()
			defer listener.Close()
			ctx, cancel := context.WithCancel(context.Background())
			expected := context.Canceled
			if deadline {
				cancel()
				ctx, cancel = context.WithTimeout(context.Background(), 200*time.Millisecond)
				expected = context.DeadlineExceeded
			}
			defer cancel()
			ready := make(chan struct{})
			done := make(chan error, 1)
			go func() {
				done <- serve(ctx, testOptions(),
					func(context.Context, string, string) (net.Listener, error) { return listener, nil },
					func(string) error { close(ready); return nil })
			}()
			select {
			case <-ready:
			case <-time.After(time.Second):
				t.Fatal("listener did not become ready")
			}
			if !deadline {
				cancel()
			}
			select {
			case err := <-done:
				if !errors.Is(err, expected) {
					t.Fatalf("got %v; wanted %v", err, expected)
				}
			case <-time.After(time.Second):
				t.Fatal("Accept was not released")
			}
		})
	}
}

func TestFailedReadinessClosesListener(t *testing.T) {
	listener := newPipeListener()
	want := errors.New("stdout unavailable")
	err := serve(context.Background(), testOptions(),
		func(context.Context, string, string) (net.Listener, error) { return listener, nil },
		func(string) error { return want })
	if !errors.Is(err, want) {
		t.Fatal(err)
	}
	select {
	case <-listener.closed:
	default:
		t.Fatal("listener remained open after failed readiness")
	}
}

func TestCLIRejectsInvalidOptionsBeforeListening(t *testing.T) {
	for _, args := range [][]string{
		{}, {"--listen", "0.0.0.0:46001"}, {"--listen", "example.com:46001"},
		{"--listen", "8.8.8.8:46001"}, {"--listen", "[::1]:46001"}, {"--listen", "127.0.0.1:80"},
		{"--listen", "127.0.0.1:46001", "--duration", "31s"},
		{"--listen", "127.0.0.1:46001", "--duration", "0s"},
		{"--listen", "127.0.0.1:46001", "--connections", "0"},
		{"--listen", "127.0.0.1:46001", "--connections", "101"},
		{"--listen", "127.0.0.1:46001", "extra"},
	} {
		t.Run(strings.Join(args, " "), func(t *testing.T) {
			var stdout, stderr bytes.Buffer
			code := run(context.Background(), args, &stdout, &stderr,
				func(context.Context, string, string) (net.Listener, error) {
					t.Fatal("invalid options opened a listener")
					return nil, nil
				})
			if code != 2 || stdout.Len() != 0 || stderr.Len() == 0 {
				t.Fatalf("code=%d stdout=%q stderr=%q", code, &stdout, &stderr)
			}
		})
	}
}

func TestCLIListenFailureDoesNotAnnounceReadiness(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := run(context.Background(), []string{"--listen", "127.0.0.1:46001"}, &stdout, &stderr,
		func(context.Context, string, string) (net.Listener, error) { return nil, errors.New("address in use") })
	if code != 1 || stdout.Len() != 0 || !strings.Contains(stderr.String(), "address in use") {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, &stdout, &stderr)
	}
}

func TestLoopbackEndpoint(t *testing.T) {
	config := net.ListenConfig{}
	listener, err := config.Listen(context.Background(), "tcp4", "127.0.0.1:0")
	if errors.Is(err, syscall.EPERM) || errors.Is(err, syscall.EACCES) {
		t.Skipf("loopback socket denied in this environment: %v", err)
	}
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	o := testOptions()
	o.address = listener.Addr().String()
	o.connections = 1
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	ready := make(chan struct{})
	done := make(chan error, 1)
	go func() {
		done <- serve(ctx, o,
			func(context.Context, string, string) (net.Listener, error) { return listener, nil },
			func(string) error { close(ready); return nil })
	}()
	select {
	case <-ready:
	case <-ctx.Done():
		t.Fatal(ctx.Err())
	}
	connection, err := (&net.Dialer{}).DialContext(ctx, "tcp4", o.address)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	connection.SetReadDeadline(time.Now().Add(time.Second))
	if payload, err := io.ReadAll(connection); len(payload) != 0 || err != nil {
		t.Fatalf("payload=%q err=%v", payload, err)
	}
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-ctx.Done():
		t.Fatal(ctx.Err())
	}
}
