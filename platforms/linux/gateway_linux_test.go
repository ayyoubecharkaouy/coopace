//go:build linux && !android

package linux

import (
	"context"
	"errors"
	"os"
	"strings"
	"testing"
	"time"
)

func TestGatewayCommandBoundsOutputAndCancelsHungProcess(t *testing.T) {
	// The test binary is a local helper, requiring no installed network tools.
	path, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("COOPACE_GATEWAY_TEST_HELPER", "flood")
	if _, err := runGatewayQuery(context.Background(), path, "-test.run=^TestGatewayCommandHelper$"); err == nil {
		t.Fatal("oversized command output accepted")
	}
	t.Setenv("COOPACE_GATEWAY_TEST_HELPER", "wait")
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	if _, err := runGatewayQuery(ctx, path, "-test.run=^TestGatewayCommandHelper$"); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("command did not honor deadline: %v", err)
	}
}

func TestGatewayCommandHelper(t *testing.T) {
	switch os.Getenv("COOPACE_GATEWAY_TEST_HELPER") {
	case "flood":
		os.Stdout.WriteString(strings.Repeat("x", gatewayOutputLimit+1))
		os.Exit(0)
	case "wait":
		time.Sleep(10 * time.Second)
		os.Exit(0)
	}
}
