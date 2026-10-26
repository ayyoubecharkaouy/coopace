//go:build linux && !android

package group

import (
	"context"
	"crypto/tls"
	"errors"
	"net"
	"path/filepath"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/identity"
	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/observe"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func testPair(t *testing.T, shareA, shareB bool) (endpoint, endpoint, string, string) {
	t.Helper()
	aDir, bDir := filepath.Join(t.TempDir(), "a"), filepath.Join(t.TempDir(), "b")
	a, err := identity.Init(aDir)
	if err != nil {
		t.Fatal(err)
	}
	b, err := identity.Init(bDir)
	if err != nil {
		t.Fatal(err)
	}
	aPublic, _ := a.Public()
	bPublic, _ := b.Public()
	aPEM, err := identity.ExportCertificate(aDir)
	if err != nil {
		t.Fatal(err)
	}
	bPEM, err := identity.ExportCertificate(bDir)
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range []struct {
		dir   string
		peer  core.DeviceID
		data  []byte
		share bool
	}{
		{aDir, bPublic.DeviceID, bPEM, shareA}, {bDir, aPublic.DeviceID, aPEM, shareB},
	} {
		_, err := Configure(entry.dir, Configuration{GroupID: "test-group", PeerID: entry.peer, PeerCertificate: entry.data, Join: true, ShareObservations: entry.share})
		if err != nil {
			t.Fatal(err)
		}
	}
	aEnd, err := loadEndpoint(aDir)
	if err != nil {
		t.Fatal(err)
	}
	bEnd, err := loadEndpoint(bDir)
	if err != nil {
		t.Fatal(err)
	}
	return aEnd, bEnd, aDir, bDir
}

func sampleReport() (observe.Report, error) {
	return observe.Report{FinishedAt: time.Now(), Elapsed: time.Second, Source: "Linux /proc/net/dev",
		Interfaces: []core.InterfaceObservation{{Name: "eth0", State: core.TrafficMeasured, Traffic: &core.InterfaceTraffic{ReceivedBytes: ^uint64(0), SentBytes: 0}}, {Name: "gone", State: core.TrafficDisappeared}}}, nil
}

type outcome struct {
	result Result
	err    error
}

func exchangePair(t *testing.T, a, b endpoint) (outcome, outcome) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	left, right := net.Pipe()
	server := make(chan outcome, 1)
	go func() { result, err := b.exchange(ctx, right, false); server <- outcome{result, err} }()
	result, err := a.exchange(ctx, left, true)
	return outcome{result, err}, <-server
}

func TestMutualTLSExchangeHonorsEachSharingChoice(t *testing.T) {
	for _, sharing := range [][2]bool{{false, false}, {true, false}, {false, true}, {true, true}} {
		t.Run(boolName(sharing[0])+"_"+boolName(sharing[1]), func(t *testing.T) {
			a, b, _, _ := testPair(t, sharing[0], sharing[1])
			var aCalls, bCalls atomic.Int32
			a.collect = func() (observe.Report, error) { aCalls.Add(1); return sampleReport() }
			b.collect = func() (observe.Report, error) { bCalls.Add(1); return sampleReport() }
			client, server := exchangePair(t, a, b)
			if client.err != nil || server.err != nil {
				t.Fatalf("exchange failed: client=%v server=%v", client.err, server.err)
			}
			if client.result.Peer.ID != a.profile.PeerID || server.result.Peer.ID != b.profile.PeerID {
				t.Fatal("wrong authenticated peer")
			}
			if client.result.SentObservation != sharing[0] || server.result.SentObservation != sharing[1] || (client.result.Received != nil) != sharing[1] || (server.result.Received != nil) != sharing[0] {
				t.Fatal("sharing choices were not independent")
			}
			if (aCalls.Load() == 1) != sharing[0] || (bCalls.Load() == 1) != sharing[1] {
				t.Fatal("collector called without sharing consent")
			}
			if sharing[0] && (*server.result.Received.Interfaces[0].ReceivedBytes != "18446744073709551615" || server.result.Received.Interfaces[1].ReceivedBytes != nil) {
				t.Fatal("received observation lost counter precision or missing values")
			}
		})
	}
}

func boolName(value bool) string {
	if value {
		return "share"
	}
	return "private"
}

func TestExchangeRejectsUnapprovedKeyAndWrongGroupBeforeCollection(t *testing.T) {
	for _, wrongGroup := range []bool{false, true} {
		a, b, _, _ := testPair(t, true, true)
		if wrongGroup {
			b.profile.Consent.GroupID = "another-group"
		} else {
			_, stranger, _, _ := testPair(t, false, false)
			b.certificate = stranger.certificate
		}
		var calls atomic.Int32
		a.collect = func() (observe.Report, error) { calls.Add(1); return sampleReport() }
		b.collect = a.collect
		client, server := exchangePair(t, a, b)
		if client.err == nil || server.err == nil {
			t.Fatalf("invalid peer/group accepted: %v %v", client.err, server.err)
		}
		if calls.Load() != 0 {
			t.Fatal("sample collected before authentication and group validation")
		}
	}
}

func TestTLSRequiresClientCertificate(t *testing.T) {
	a, b, _, _ := testPair(t, false, false)
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	left, right := net.Pipe()
	defer left.Close()
	stop := context.AfterFunc(ctx, func() { left.Close(); right.Close() })
	defer stop()
	config := a.tlsConfig(true)
	config.Certificates = nil
	server := make(chan error, 1)
	go func() { defer right.Close(); server <- tls.Server(right, b.tlsConfig(false)).HandshakeContext(ctx) }()
	client := tls.Client(left, config)
	_ = client.HandshakeContext(ctx)
	// TLS 1.3 client Handshake may return before the server rejects its empty cert.
	_, _ = client.Read(make([]byte, 1))
	if err := <-server; err == nil {
		t.Fatal("server accepted a client without its certificate")
	}
}

func TestRevocationInterruptsBlockedTLSExchange(t *testing.T) {
	a, b, aDir, _ := testPair(t, true, false)
	parent, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	ctx, stop := watchApproval(parent, a.check)
	defer stop()
	left, right := net.Pipe()
	defer right.Close()
	ready, serverDone := make(chan error, 1), make(chan struct{})
	go func() {
		defer close(serverDone)
		defer right.Close()
		err := tls.Server(right, b.tlsConfig(false)).HandshakeContext(ctx)
		ready <- err
		if err == nil {
			<-ctx.Done()
		} // intentionally never read the client's hello
	}()
	clientDone := make(chan error, 1)
	go func() { _, err := a.exchange(ctx, left, true); clientDone <- err }()
	if err := <-ready; err != nil {
		t.Fatal(err)
	}
	if err := Revoke(aDir); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-clientDone:
		if err == nil || context.Cause(ctx) == nil || errors.Is(context.Cause(ctx), context.DeadlineExceeded) {
			t.Fatalf("revocation did not abort exchange: %v, cause %v", err, context.Cause(ctx))
		}
	case <-time.After(time.Second):
		t.Fatal("revocation did not unblock connection")
	}
	<-serverDone
}

func TestRevocationDuringCollectionPreventsSendingObservation(t *testing.T) {
	a, b, aDir, _ := testPair(t, true, false)
	a.collect = func() (observe.Report, error) {
		if err := Revoke(aDir); err != nil {
			return observe.Report{}, err
		}
		return sampleReport()
	}
	client, server := exchangePair(t, a, b)
	if client.err == nil || server.err == nil || server.result.Received != nil {
		t.Fatal("observation sent after consent changed")
	}
}

func TestGroupLoopbackExchange(t *testing.T) {
	_, _, aDir, bDir := testPair(t, false, false)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ready, done := make(chan string, 1), make(chan outcome, 1)
	go func() {
		result, err := Listen(ctx, bDir, "127.0.0.1:0", func(address string) error { ready <- address; return nil })
		done <- outcome{result, err}
	}()
	select {
	case early := <-done:
		if errors.Is(early.err, syscall.EPERM) || errors.Is(early.err, syscall.EACCES) {
			t.Skipf("loopback sockets unavailable: %v", early.err)
		}
		t.Fatalf("listener failed: %v", early.err)
	case address := <-ready:
		result, err := Exchange(ctx, aDir, address)
		server := <-done
		if err != nil || server.err != nil || result.Peer.ID == "" || result.SentObservation || result.Received != nil {
			t.Fatalf("loopback exchange failed: %v / %v", err, server.err)
		}
	case <-ctx.Done():
		t.Fatal(ctx.Err())
	}
}
