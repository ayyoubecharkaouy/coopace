package identity

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const certificateFile = "identity.crt"

// CertificateName binds hostname verification to the approved public key.
func CertificateName(id core.DeviceID) string {
	digest := strings.TrimPrefix(string(id), "ed25519:")
	if len(digest) != 64 {
		return ""
	}
	// Split the fingerprint so neither DNS label exceeds 63 octets.
	return "coopace-" + digest[:32] + "." + digest[32:] + ".invalid"
}

// ParseCertificate accepts one currently valid, self-signed Ed25519 leaf.
// The caller must obtain expectedID through an independent approval channel.
func ParseCertificate(data []byte, expectedID core.DeviceID) (*x509.Certificate, error) {
	if len(data) > 16384 || !bytes.HasPrefix(data, []byte("-----BEGIN CERTIFICATE-----")) {
		return nil, fmt.Errorf("invalid public certificate encoding or size")
	}
	block, rest := pem.Decode(data)
	if block == nil || block.Type != "CERTIFICATE" || len(block.Headers) != 0 || len(bytes.TrimSpace(rest)) != 0 {
		return nil, fmt.Errorf("expected exactly one public certificate")
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("invalid public certificate")
	}
	key, ok := cert.PublicKey.(ed25519.PublicKey)
	if !ok {
		return nil, fmt.Errorf("certificate requires an Ed25519 public key")
	}
	id, err := core.DeviceIDForPublicKey(key)
	if err != nil || id != expectedID {
		return nil, fmt.Errorf("certificate does not match approved device fingerprint")
	}
	if cert.IsCA || !cert.BasicConstraintsValid || cert.KeyUsage != x509.KeyUsageDigitalSignature {
		return nil, fmt.Errorf("expected a signing leaf certificate")
	}
	if err := cert.CheckSignature(cert.SignatureAlgorithm, cert.RawTBSCertificate, cert.Signature); err != nil {
		return nil, fmt.Errorf("certificate is not self-signed")
	}
	roots := x509.NewCertPool()
	roots.AddCert(cert)
	for _, usage := range []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth, x509.ExtKeyUsageClientAuth} {
		if _, err := cert.Verify(x509.VerifyOptions{Roots: roots, DNSName: CertificateName(id), KeyUsages: []x509.ExtKeyUsage{usage}}); err != nil {
			return nil, fmt.Errorf("certificate validity or usage: %w", err)
		}
	}
	return cert, nil
}

// ExportCertificate creates a public certificate once for an existing identity.
// Existing invalid/expired certificates are never silently replaced.
func ExportCertificate(directory string) ([]byte, error) {
	i, err := Load(directory)
	if err != nil {
		return nil, err
	}
	path := filepath.Join(directory, certificateFile)
	if _, err := os.Lstat(path); err == nil {
		_, data, err := loadCertificate(directory, i)
		return data, err
	} else if !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	public, _ := i.Public()
	serial, err := rand.Int(rand.Reader, new(big.Int).Lsh(big.NewInt(1), 128))
	if err != nil {
		return nil, err
	}
	serial.Add(serial, big.NewInt(1))
	now := time.Now()
	template := &x509.Certificate{
		SerialNumber: serial, Subject: pkix.Name{CommonName: "Coopace agent"},
		DNSNames: []string{CertificateName(public.DeviceID)}, NotBefore: now.Add(-5 * time.Minute), NotAfter: now.Add(365 * 24 * time.Hour),
		BasicConstraintsValid: true, KeyUsage: x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth, x509.ExtKeyUsageClientAuth},
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, i.privateKey.Public(), i.privateKey)
	if err != nil {
		return nil, err
	}
	data := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if errors.Is(err, os.ErrExist) {
		_, data, err := loadCertificate(directory, i)
		return data, err
	}
	if err != nil {
		return nil, err
	}
	if _, err = file.Write(data); err == nil {
		err = file.Sync()
	}
	closeErr := file.Close()
	if err == nil {
		err = closeErr
	}
	if err != nil {
		os.Remove(path)
		return nil, err
	}
	_, data, err = loadCertificate(directory, i)
	return data, err
}

// LoadTLS never initializes identity material or rotates certificates.
func LoadTLS(directory string) (tls.Certificate, error) {
	i, err := Load(directory)
	if err != nil {
		return tls.Certificate{}, err
	}
	cert, _, err := loadCertificate(directory, i)
	if err != nil {
		return tls.Certificate{}, err
	}
	return tls.Certificate{Certificate: [][]byte{cert.Raw}, PrivateKey: i.privateKey, Leaf: cert}, nil
}

func loadCertificate(directory string, i Identity) (*x509.Certificate, []byte, error) {
	path := filepath.Join(directory, certificateFile)
	info, err := os.Lstat(path)
	if err != nil {
		return nil, nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, nil, fmt.Errorf("certificate must be a regular file")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, nil, err
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, 16385))
	if err != nil {
		return nil, nil, err
	}
	public, _ := i.Public()
	cert, err := ParseCertificate(data, public.DeviceID)
	return cert, data, err
}
