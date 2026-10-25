package linux

import (
	"errors"
	"io"
	"strings"
	"testing"
)

const headers = "Inter-| Receive | Transmit\n face |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed\n"

func TestParseTrafficCounters(t *testing.T) {
	input := headers + "    lo: 0 1 2 3 4 5 6 7 0 9 10 11 12 13 14 15\n" +
		" eth0: 18446744073709551615 1 2 3 4 5 6 7 200 9 10 11 12 13 14 15\n"
	counters, err := parseTrafficCounters(strings.NewReader(input))
	if err != nil {
		t.Fatal(err)
	}
	if len(counters) != 2 || counters[0].Name != "lo" || counters[0].ReceivedBytes != 0 || counters[0].SentBytes != 0 ||
		counters[1].Name != "eth0" || counters[1].ReceivedBytes != ^uint64(0) || counters[1].SentBytes != 200 {
		t.Fatalf("incorrect receive/transmit fields: %+v", counters)
	}
}

func TestParseTrafficRejectsMalformedInput(t *testing.T) {
	for _, input := range []string{
		"", "unrecognized\nheader\n", headers + "eth0 1 2 3\n", headers + "eth0: 1 2 3\n",
		headers + "eth0: -1 0 0 0 0 0 0 0 2 0 0 0 0 0 0 0\n",
		headers + "eth0: 18446744073709551616 0 0 0 0 0 0 0 2 0 0 0 0 0 0 0\n",
		headers + "eth0: 1 0 0 0 0 0 0 0 invalid 0 0 0 0 0 0 0\n",
	} {
		if _, err := parseTrafficCounters(strings.NewReader(input)); err == nil {
			t.Errorf("malformed input accepted: %q", input)
		}
	}
}

type failedReader struct{ err error }

func (r failedReader) Read([]byte) (int, error) { return 0, r.err }

func TestParseTrafficPropagatesReadFailure(t *testing.T) {
	want := errors.New("read failed")
	_, err := parseTrafficCounters(io.MultiReader(strings.NewReader(headers), failedReader{want}))
	if !errors.Is(err, want) {
		t.Fatalf("read failure lost: %v", err)
	}
}
