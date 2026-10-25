package latency

import (
	"context"
	"errors"
	"io"
	"net"
	"syscall"
	"testing"
	"time"
)

func TestProbeLoopbackConnectsAndClosesWithoutPayload(t *testing.T) {
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if errors.Is(err, syscall.EPERM) || errors.Is(err, syscall.EACCES) {
		t.Skipf("loopback socket denied in this environment: %v", err)
	}
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	type received struct {
		payload []byte
		err     error
	}
	result := make(chan received, 1)
	go func() {
		connection, err := listener.Accept()
		if err != nil {
			result <- received{err: err}
			return
		}
		defer connection.Close()
		connection.SetReadDeadline(time.Now().Add(2 * time.Second))
		payload, err := io.ReadAll(connection)
		result <- received{payload, err}
	}()
	sample := probeTCP(context.Background(), listener.Addr().String(), time.Second)
	if sample.Failure != "" || sample.Duration < 0 {
		t.Fatalf("local connect failed: %+v", sample)
	}
	select {
	case got := <-result:
		if got.err != nil || len(got.payload) != 0 {
			t.Fatalf("probe sent application data or did not close: %+v", got)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("probe did not close its connection")
	}
}
