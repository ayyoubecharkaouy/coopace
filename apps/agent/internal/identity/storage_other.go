//go:build !linux || android

package identity

import "fmt"

func prepareDirectory(string, bool) error {
	return fmt.Errorf("persistent identity storage is currently available only on Linux; a native protected storage adapter is required on this system")
}
