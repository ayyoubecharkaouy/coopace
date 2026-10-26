package group

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"net"
	"net/netip"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/identity"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const exchangeTimeout = 30 * time.Second
const groupALPN = "coopace-group/2"

// ValidateAddress requires an explicit numeric IP, avoiding DNS ambiguity.
func ValidateAddress(address string, listener bool) error {
	value, err := netip.ParseAddrPort(address)
	if err != nil || value.Addr().Zone() != "" || (!listener && value.Port() == 0) {
		return fmt.Errorf("expected numeric unicast IP:port (IPv6 in brackets)")
	}
	ip := value.Addr().Unmap()
	unicast := ip.IsGlobalUnicast() || ip.IsLoopback() || ip.IsLinkLocalUnicast()
	if !unicast && !(listener && ip.IsUnspecified()) {
		return fmt.Errorf("expected numeric unicast IP:port (IPv6 in brackets); wildcard IP allowed only for listening")
	}
	return nil
}

// Listen accepts exactly one connection, bounded by 30 seconds including wait.
// The caller explicitly selects the bind address; CLI defaults to loopback.
func Listen(ctx context.Context, directory, address string, ready func(string) error) (Result, error) {
	return runNetwork(ctx, directory, address, true, ready)
}

func Exchange(ctx context.Context, directory, address string) (Result, error) {
	return runNetwork(ctx, directory, address, false, nil)
}

func runNetwork(ctx context.Context, directory, address string, server bool, ready func(string) error) (Result, error) {
	if err := ValidateAddress(address, server); err != nil {
		return Result{}, err
	}
	e, err := loadEndpoint(directory)
	if err != nil {
		return Result{}, err
	}
	ctx, cancel := context.WithTimeout(ctx, exchangeTimeout)
	defer cancel()
	ctx, stopApproval := watchApproval(ctx, e.check)
	defer stopApproval()
	var conn net.Conn
	if server {
		listener, err := (&net.ListenConfig{}).Listen(ctx, "tcp", address)
		if err != nil {
			return Result{}, err
		}
		defer listener.Close()
		stopClose := context.AfterFunc(ctx, func() { listener.Close() })
		defer stopClose()
		if ready != nil {
			if err := ready(listener.Addr().String()); err != nil {
				return Result{}, err
			}
		}
		conn, err = listener.Accept()
	} else {
		conn, err = (&net.Dialer{}).DialContext(ctx, "tcp", address)
	}
	if err == nil {
		defer conn.Close()
		var result Result
		result, err = e.exchange(ctx, conn, !server)
		if err == nil {
			return result, nil
		}
	}
	if cause := context.Cause(ctx); cause != nil {
		return Result{}, cause
	}
	return Result{}, err
}

func watchApproval(parent context.Context, check func() error) (context.Context, func()) {
	ctx, cancel := context.WithCancelCause(parent)
	// The watcher also runs during accept/dial and TLS handshake. Frame boundaries
	// check synchronously; already transmitted bytes cannot be recalled.
	watchDone := make(chan struct{})
	go func() {
		defer close(watchDone)
		ticker := time.NewTicker(100 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if err := check(); err != nil {
					cancel(err)
					return
				}
			}
		}
	}()
	return ctx, func() { cancel(nil); <-watchDone }
}

func (e endpoint) tlsConfig(client bool) *tls.Config {
	roots := x509.NewCertPool()
	roots.AddCert(e.peerCertificate)
	config := &tls.Config{
		MinVersion: tls.VersionTLS13, Certificates: []tls.Certificate{e.certificate},
		RootCAs: roots, ClientCAs: roots, ClientAuth: tls.RequireAndVerifyClientCert,
		NextProtos: []string{groupALPN}, SessionTicketsDisabled: true,
	}
	if client {
		config.ServerName = identity.CertificateName(e.profile.PeerID)
	}
	config.VerifyConnection = func(state tls.ConnectionState) error {
		if len(state.VerifiedChains) == 0 || len(state.PeerCertificates) != 1 || state.NegotiatedProtocol != groupALPN || state.Version < tls.VersionTLS13 {
			return fmt.Errorf("mutually verified TLS 1.3 with Coopace ALPN is required")
		}
		key, ok := state.PeerCertificates[0].PublicKey.(ed25519.PublicKey)
		if !ok {
			return fmt.Errorf("peer key is not Ed25519")
		}
		id, err := core.DeviceIDForPublicKey(key)
		if err != nil || id != e.profile.PeerID || !bytes.Equal(state.PeerCertificates[0].Raw, e.peerCertificate.Raw) {
			return fmt.Errorf("TLS peer is not explicitly approved")
		}
		return e.check()
	}
	return config
}
