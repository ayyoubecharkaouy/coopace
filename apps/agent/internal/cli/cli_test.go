package cli

import (
	"bytes"
	"io"
	"runtime"
	"strings"
	"testing"
)

func TestStatusShowsLocalState(t *testing.T) {
	if runtime.GOOS != "linux" && runtime.GOOS != "windows" {
		t.Skip("desktop status requires Linux or Windows")
	}
	var stdout, stderr bytes.Buffer
	code := Run([]string{"status"}, "test-version", &stdout, &stderr)
	if code != 0 || stderr.Len() != 0 {
		t.Fatalf("status failed: code=%d, stderr=%q", code, stderr.String())
	}
	for _, expected := range []string{
		"Coopace test-version\n",
		"Système : " + runtime.GOOS + "\n",
		"Architecture : " + runtime.GOARCH + "\n",
		"Rôle : agent\n",
		"État : local (hors groupe)\n",
	} {
		if !strings.Contains(stdout.String(), expected) {
			t.Errorf("missing %q in output %q", expected, stdout.String())
		}
	}
}

func TestHelp(t *testing.T) {
	for _, args := range [][]string{nil, {"help"}, {"--help"}, {"-h"}} {
		var stdout, stderr bytes.Buffer
		code := Run(args, "dev", &stdout, &stderr)
		if code != 0 || !strings.Contains(stdout.String(), "coopace <commande>") || stderr.Len() != 0 {
			t.Errorf("help %v: code=%d, stdout=%q, stderr=%q", args, code, stdout.String(), stderr.String())
		}
	}
}

func TestInvalidArguments(t *testing.T) {
	for _, args := range [][]string{{"unknown"}, {"status", "extra"}, {"status", "--unknown"}, {"observe", "extra"}, {"help", "extra"}} {
		var stdout, stderr bytes.Buffer
		code := Run(args, "dev", &stdout, &stderr)
		if code != 2 || stdout.Len() != 0 || !strings.Contains(stderr.String(), "non reconnus") {
			t.Errorf("invalid args %v: code=%d, stdout=%q, stderr=%q", args, code, stdout.String(), stderr.String())
		}
	}
}

type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) {
	return 0, io.ErrClosedPipe
}

func TestOutputFailure(t *testing.T) {
	for _, args := range [][]string{{"help"}, {"status"}} {
		var stderr bytes.Buffer
		code := Run(args, "dev", failingWriter{}, &stderr)
		if code != 1 || !strings.Contains(stderr.String(), "Erreur d'affichage") {
			t.Errorf("output failure %v: code=%d, stderr=%q", args, code, stderr.String())
		}
	}
}
