package group

import (
	"context"
	"crypto/ed25519"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"net"
	"runtime"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/identity"
	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/observe"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
	"github.com/ayyoubecharkaouy/coopace/packages/protocol"
)

type Result struct {
	Peer            core.Device
	SentObservation bool
	Received        *protocol.TrafficObservation
}

type endpoint struct {
	profile         Profile
	certificate     tls.Certificate
	peerCertificate *x509.Certificate
	check           func() error
	collect         func() (observe.Report, error)
}

func loadEndpoint(directory string) (endpoint, error) {
	profile, digest, err := loadProfile(directory, true)
	if err != nil {
		return endpoint{}, err
	}
	if !profile.Consent.Join {
		return endpoint{}, fmt.Errorf("local group membership is not authorized")
	}
	certificate, err := identity.LoadTLS(directory)
	if err != nil {
		return endpoint{}, err
	}
	peer, err := identity.ParseCertificate([]byte(profile.PeerCertificate), profile.PeerID)
	if err != nil {
		return endpoint{}, err
	}
	return endpoint{profile: profile, certificate: certificate, peerCertificate: peer,
		check: func() error { return checkSnapshot(directory, digest) }, collect: observe.Local}, nil
}

// exchange runs an ordered, bounded protocol over one connection. Closing the
// underlying connection also unblocks in-memory net.Pipe TLS handshakes in tests.
func (e endpoint) exchange(ctx context.Context, raw net.Conn, client bool) (Result, error) {
	ctx, cancel := context.WithTimeout(ctx, exchangeTimeout)
	defer cancel()
	stopClose := context.AfterFunc(ctx, func() { raw.Close() })
	defer stopClose()
	defer raw.Close()
	deadline, _ := ctx.Deadline()
	if err := raw.SetDeadline(deadline); err != nil {
		return Result{}, err
	}
	if err := e.check(); err != nil {
		return Result{}, err
	}
	var conn *tls.Conn
	if client {
		conn = tls.Client(raw, e.tlsConfig(true))
	} else {
		conn = tls.Server(raw, e.tlsConfig(false))
	}
	if err := conn.HandshakeContext(ctx); err != nil {
		return Result{}, fmt.Errorf("TLS authentication: %w", err)
	}
	// Derive the protocol identity from the certificate actually authenticated.
	key := conn.ConnectionState().PeerCertificates[0].PublicKey.(ed25519.PublicKey)
	peerID, _ := core.DeviceIDForPublicKey(key)
	session, err := protocol.NewSession(e.profile.Consent.GroupID, string(peerID))
	if err != nil {
		return Result{}, err
	}
	sequence := uint64(0)
	send := func(kind string, hello *protocol.Hello, observation *protocol.TrafficObservation) error {
		if err := e.check(); err != nil {
			return err
		}
		if err := ctx.Err(); err != nil {
			return err
		}
		sequence++
		return protocol.WriteFrame(conn, protocol.Message{Version: protocol.Version, Kind: kind, GroupID: e.profile.Consent.GroupID,
			SenderID: string(e.profile.Consent.DeviceID), Sequence: sequence, Hello: hello, Observation: observation})
	}
	receive := func(kind string) (protocol.Message, error) {
		if err := e.check(); err != nil {
			return protocol.Message{}, err
		}
		data, err := protocol.ReadFrame(conn)
		if err != nil {
			return protocol.Message{}, err
		}
		if err := e.check(); err != nil {
			return protocol.Message{}, err
		}
		message, err := session.Next(data)
		if err != nil {
			return protocol.Message{}, err
		}
		if message.Kind != kind {
			return protocol.Message{}, fmt.Errorf("unexpected message kind: %s", message.Kind)
		}
		return message, nil
	}
	hello := &protocol.Hello{Name: e.profile.Name, OS: runtime.GOOS, Roles: []string{"agent"}, Capabilities: []string{}, ShareObservations: e.profile.Consent.ShareObservations}
	var remote protocol.Message
	if client {
		if err = send(protocol.HelloKind, hello, nil); err == nil {
			remote, err = receive(protocol.HelloKind)
		}
	} else {
		remote, err = receive(protocol.HelloKind)
		if err == nil {
			if _, err = DeviceFromHello(remote); err == nil {
				err = send(protocol.HelloKind, hello, nil)
			}
		}
	}
	if err != nil {
		return Result{}, err
	}
	peer, err := DeviceFromHello(remote)
	if err != nil {
		return Result{}, err
	}
	result := Result{Peer: peer}
	sendObservation := func() error {
		if !e.profile.Consent.AllowsObservationSharing(e.profile.Consent.GroupID, e.profile.Consent.DeviceID) {
			return nil
		}
		if err := e.check(); err != nil {
			return err
		}
		if err := ctx.Err(); err != nil {
			return err
		}
		report, err := e.collect()
		if err != nil {
			return err
		}
		observation, err := wireObservation(report)
		if err != nil {
			return err
		}
		if err := send(protocol.TrafficKind, nil, observation); err != nil {
			return err
		}
		result.SentObservation = true
		return nil
	}
	receiveObservation := func() error {
		if !remote.Hello.ShareObservations {
			return nil
		}
		message, err := receive(protocol.TrafficKind)
		if err == nil {
			result.Received = message.Observation
		}
		return err
	}
	if client {
		if err = sendObservation(); err == nil {
			err = receiveObservation()
		}
		if err == nil {
			_, err = receive(protocol.CompleteKind)
		}
		if err == nil {
			err = send(protocol.CompleteKind, nil, nil)
		}
	} else {
		if err = receiveObservation(); err == nil {
			err = sendObservation()
		}
		if err == nil {
			err = send(protocol.CompleteKind, nil, nil)
		}
		if err == nil {
			_, err = receive(protocol.CompleteKind)
		}
	}
	if err != nil {
		return Result{}, err
	}
	return result, nil
}
