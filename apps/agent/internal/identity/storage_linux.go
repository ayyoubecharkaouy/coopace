//go:build linux && !android

package identity

import (
	"fmt"
	"os"
	"strings"
)

func prepareDirectory(path string, create bool) error {
	if strings.TrimSpace(path) == "" {
		return fmt.Errorf("an explicit state directory is required")
	}
	if create {
		if err := os.MkdirAll(path, 0700); err != nil {
			return err
		}
	}
	info, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if !info.IsDir() || info.Mode().Perm()&0077 != 0 {
		return fmt.Errorf("identity state directory must be private (mode 0700) and not a symlink")
	}
	return nil
}
