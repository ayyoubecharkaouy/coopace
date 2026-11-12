package snapshot

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"path/filepath"
)

// SaveExclusive publishes a complete, validated JSON file with mode 0600.
// Linking the synchronized temporary file makes publication atomic and refuses
// existing destinations, including symlinks. This is not a recovery journal or
// a guarantee of directory-entry persistence after a machine power loss.
func SaveExclusive(ctx context.Context, path string, report Report) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	var data bytes.Buffer
	if err := WriteJSON(&data, report); err != nil {
		return err
	}
	if _, err := Read(ctx, bytes.NewReader(data.Bytes())); err != nil {
		return err
	}
	file, err := os.CreateTemp(filepath.Dir(path), ".coopace-snapshot-*")
	if err != nil {
		return err
	}
	defer os.Remove(file.Name())
	defer file.Close()
	if _, err := file.Write(data.Bytes()); err != nil {
		return err
	}
	if err := file.Sync(); err != nil {
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := os.Link(file.Name(), path); err != nil {
		return fmt.Errorf("publication de la capture (destination neuve requise) : %w", err)
	}
	return nil
}
