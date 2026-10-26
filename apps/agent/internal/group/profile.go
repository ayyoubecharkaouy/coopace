package group

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/identity"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
	"github.com/ayyoubecharkaouy/coopace/packages/protocol"
)

const profileFile = "group.json"
const maxProfileBytes = 32768

// Profile is one local approval, not a shared group authority or live session.
type Profile struct {
	Version         int               `json:"version"`
	Name            string            `json:"name"`
	Consent         core.GroupConsent `json:"consent"`
	PeerID          core.DeviceID     `json:"peer_id"`
	PeerCertificate string            `json:"peer_certificate"`
}

type Configuration struct {
	GroupID           string
	Name              string
	PeerID            core.DeviceID
	PeerCertificate   []byte
	Join              bool
	ShareObservations bool
}

// Configure explicitly replaces the single local peer approval and consent.
func Configure(directory string, options Configuration) (Profile, error) {
	_, err := identity.LoadTLS(directory)
	if err != nil {
		return Profile{}, fmt.Errorf("prepare identity and export-cert first: %w", err)
	}
	local, err := identity.Load(directory)
	if err != nil {
		return Profile{}, err
	}
	public, _ := local.Public()
	if !options.Join {
		return Profile{}, fmt.Errorf("explicit --join consent is required")
	}
	name := options.Name
	if name == "" {
		name = "Coopace agent"
	}
	profile := Profile{Version: 1, Name: name, PeerID: options.PeerID, PeerCertificate: string(options.PeerCertificate),
		Consent: core.GroupConsent{GroupID: options.GroupID, DeviceID: public.DeviceID, Join: true, ShareObservations: options.ShareObservations}}
	if err := validateProfile(profile, public.DeviceID, true); err != nil {
		return Profile{}, err
	}
	return profile, saveProfile(directory, profile)
}

func validateProfile(profile Profile, self core.DeviceID, verifyCertificate bool) error {
	if profile.Version != 1 || profile.Consent.DeviceID != self || profile.PeerID == self || profile.Consent.AllowRelay {
		return fmt.Errorf("invalid profile version, identity, peer or relay permission")
	}
	if err := profile.Consent.Validate(); err != nil {
		return err
	}
	// Reuse the wire bounds for the device name and both identity fingerprints.
	for _, id := range []core.DeviceID{self, profile.PeerID} {
		if _, err := protocol.Encode(protocol.Message{Version: protocol.Version, Kind: protocol.HelloKind, GroupID: profile.Consent.GroupID,
			SenderID: string(id), Sequence: 1, Hello: &protocol.Hello{Name: profile.Name, OS: "linux", Roles: []string{"agent"}}}); err != nil {
			return err
		}
	}
	if verifyCertificate {
		_, err := identity.ParseCertificate([]byte(profile.PeerCertificate), profile.PeerID)
		return err
	}
	return nil
}

func LoadProfile(directory string) (Profile, error) {
	// Showing/revoking a stored approval remains possible after certificate expiry.
	profile, _, err := loadProfile(directory, false)
	return profile, err
}

func loadProfile(directory string, verifyCertificate bool) (Profile, [32]byte, error) {
	local, err := identity.Load(directory)
	if err != nil {
		return Profile{}, [32]byte{}, err
	}
	data, err := readProfile(directory)
	if err != nil {
		return Profile{}, [32]byte{}, err
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var profile Profile
	if err := decoder.Decode(&profile); err != nil {
		return Profile{}, [32]byte{}, fmt.Errorf("invalid group profile: %w", err)
	}
	if decoder.Decode(new(any)) != io.EOF {
		return Profile{}, [32]byte{}, fmt.Errorf("trailing group profile data")
	}
	public, _ := local.Public()
	if err := validateProfile(profile, public.DeviceID, verifyCertificate); err != nil {
		return Profile{}, [32]byte{}, err
	}
	return profile, sha256.Sum256(data), nil
}

func Revoke(directory string) error {
	// Expiration of the peer's certificate must not prevent local revocation.
	profile, _, err := loadProfile(directory, false)
	if err != nil {
		return err
	}
	profile.Consent.Join = false
	profile.Consent.ShareObservations = false
	return saveProfile(directory, profile)
}

func readProfile(directory string) ([]byte, error) {
	path := filepath.Join(directory, profileFile)
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
		return nil, fmt.Errorf("group profile must be a private regular file (mode 0600)")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, maxProfileBytes+1))
	if err != nil {
		return nil, err
	}
	if len(data) > maxProfileBytes {
		return nil, fmt.Errorf("group profile exceeds size limit")
	}
	return data, nil
}

func saveProfile(directory string, profile Profile) error {
	data, err := json.MarshalIndent(profile, "", "  ")
	if err != nil {
		return err
	}
	if len(data) > maxProfileBytes {
		return fmt.Errorf("group profile exceeds size limit")
	}
	path := filepath.Join(directory, profileFile)
	if info, err := os.Lstat(path); err == nil {
		if !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
			return fmt.Errorf("refusing to replace nonprivate or nonregular profile")
		}
	} else if !os.IsNotExist(err) {
		return err
	}
	file, err := os.CreateTemp(directory, ".group-*") // mode 0600
	if err != nil {
		return err
	}
	defer os.Remove(file.Name())
	if _, err = file.Write(data); err == nil {
		err = file.Sync()
	}
	closeErr := file.Close()
	if err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	if err := os.Rename(file.Name(), path); err != nil {
		return err
	}
	// Persist the directory entry as well as the contents, including revocation.
	folder, err := os.Open(directory)
	if err != nil {
		return err
	}
	defer folder.Close()
	return folder.Sync()
}

func checkSnapshot(directory string, expected [32]byte) error {
	data, err := readProfile(directory)
	if err != nil {
		return err
	}
	if sha256.Sum256(data) != expected {
		return fmt.Errorf("local group approval changed or was revoked; start a new exchange")
	}
	return nil
}
