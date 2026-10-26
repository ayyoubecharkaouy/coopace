//go:build linux && !android

package identity

import (
	"bytes"
	"crypto/rand"
	"crypto/x509"
	"encoding/pem"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestCertificateIsPublicStableAndBoundToExistingKey(t *testing.T) {
	directory := filepath.Join(t.TempDir(), "state")
	i, err := Init(directory)
	if err != nil {
		t.Fatal(err)
	}
	public, _ := i.Public()
	for _, label := range strings.Split(CertificateName(public.DeviceID), ".") {
		if len(label) == 0 || len(label) > 63 {
			t.Fatal("fingerprint hostname has an invalid DNS label length")
		}
	}
	data, err := ExportCertificate(directory)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(data, []byte("PRIVATE KEY")) {
		t.Fatal("private key exported")
	}
	again, err := ExportCertificate(directory)
	if err != nil || !bytes.Equal(again, data) {
		t.Fatalf("certificate rotated: %v", err)
	}
	loaded, err := LoadTLS(directory)
	if err != nil || !bytes.Equal(loaded.Certificate[0], loaded.Leaf.Raw) {
		t.Fatalf("cannot load TLS identity: %v", err)
	}
	if _, err := ParseCertificate(data, public.DeviceID); err != nil {
		t.Fatal(err)
	}
	for _, invalid := range [][]byte{[]byte("invalid"), append(append([]byte(nil), data...), data...), append([]byte("junk"), data...)} {
		if _, err := ParseCertificate(invalid, public.DeviceID); err == nil {
			t.Fatal("invalid certificate accepted")
		}
	}
	if _, err := ParseCertificate(data, core.DeviceID("ed25519:"+strings.Repeat("a", 64))); err == nil {
		t.Fatal("wrong approved fingerprint accepted")
	}
	if err := os.WriteFile(filepath.Join(directory, certificateFile), []byte("corrupt"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := ExportCertificate(directory); err == nil {
		t.Fatal("corrupt certificate silently replaced")
	}
	if _, err := ExportCertificate(filepath.Join(t.TempDir(), "missing")); err == nil {
		t.Fatal("export implicitly initialized identity")
	}
}

func TestCertificateRejectsExpirationAndWrongUsage(t *testing.T) {
	i, err := generate()
	if err != nil {
		t.Fatal(err)
	}
	public, _ := i.Public()
	directory := filepath.Join(t.TempDir(), "state")
	if _, err := Init(directory); err != nil {
		t.Fatal(err)
	}
	data, err := ExportCertificate(directory)
	if err != nil {
		t.Fatal(err)
	}
	block, _ := pem.Decode(data)
	template, _ := x509.ParseCertificate(block.Bytes)
	template.PublicKey = i.privateKey.Public()
	template.DNSNames = []string{CertificateName(public.DeviceID)}
	for _, expired := range []bool{true, false} {
		if expired {
			template.NotAfter = time.Now().Add(-time.Hour)
		} else {
			template.NotAfter = time.Now().Add(time.Hour)
			template.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}
		}
		der, err := x509.CreateCertificate(rand.Reader, template, template, i.privateKey.Public(), i.privateKey)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := ParseCertificate(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), public.DeviceID); err == nil {
			t.Fatal("expired or unsuitable certificate accepted")
		}
	}
}
