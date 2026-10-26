package identity

import (
	"bytes"
	"crypto/ed25519"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

const keyFile = "identity.key"

// Init creates one identity exclusively, or loads an existing one without rotation.
func Init(stateDirectory string) (Identity, error) {
	if err := prepareDirectory(stateDirectory, true); err != nil {
		return Identity{}, err
	}
	path := filepath.Join(stateDirectory, keyFile)
	if _, err := os.Lstat(path); err == nil {
		return Load(stateDirectory)
	} else if !errors.Is(err, os.ErrNotExist) {
		return Identity{}, err
	}
	identity, err := generate()
	if err != nil {
		return Identity{}, err
	}
	data, err := x509.MarshalPKCS8PrivateKey(identity.privateKey)
	if err != nil {
		return Identity{}, err
	}
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if errors.Is(err, os.ErrExist) {
		return Load(stateDirectory)
	}
	if err != nil {
		return Identity{}, err
	}
	encoded := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: data})
	if _, err = file.Write(encoded); err == nil {
		err = file.Sync()
	}
	closeError := file.Close()
	if err == nil {
		err = closeError
	}
	if err != nil {
		os.Remove(path)
		return Identity{}, fmt.Errorf("saving identity: %w", err)
	}
	return Load(stateDirectory)
}

// Load never creates, replaces, or repairs an identity implicitly.
func Load(stateDirectory string) (Identity, error) {
	if err := prepareDirectory(stateDirectory, false); err != nil {
		return Identity{}, err
	}
	path := filepath.Join(stateDirectory, keyFile)
	info, err := os.Lstat(path)
	if err != nil {
		return Identity{}, err
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
		return Identity{}, fmt.Errorf("identity key must be a private regular file (mode 0600)")
	}
	file, err := os.Open(path)
	if err != nil {
		return Identity{}, err
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, 16385))
	if err != nil {
		return Identity{}, err
	}
	if len(data) > 16384 {
		return Identity{}, fmt.Errorf("identity key file is too large")
	}
	block, rest := pem.Decode(data)
	if block == nil || block.Type != "PRIVATE KEY" || len(bytes.TrimSpace(rest)) != 0 {
		return Identity{}, fmt.Errorf("invalid identity key encoding")
	}
	key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return Identity{}, fmt.Errorf("invalid PKCS8 identity key")
	}
	privateKey, ok := key.(ed25519.PrivateKey)
	if !ok || len(privateKey) != ed25519.PrivateKeySize {
		return Identity{}, fmt.Errorf("identity requires an Ed25519 private key")
	}
	return Identity{privateKey: privateKey}, nil
}
