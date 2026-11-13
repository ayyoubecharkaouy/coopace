package core

import (
	"strings"
	"testing"
)

func TestGatewaySessionRequiresConsentAndBoundReference(t *testing.T) {
	sha := strings.Repeat("a", 64)
	for _, tc := range []struct {
		reference CakeReferenceID
		sha       string
		consent   bool
	}{
		{CakeReferenceIPv4LabV1, sha, false}, {"household", sha, true},
		{CakeReferenceIPv4LabV1, "", true}, {CakeReferenceIPv4LabV1, strings.ToUpper(sha), true},
	} {
		if _, err := NewGatewaySession(tc.reference, tc.sha, tc.consent); err == nil {
			t.Fatal("invalid launch accepted", tc)
		}
	}
}

func TestGatewaySessionLifecycleAndPermanentRefusal(t *testing.T) {
	sha := strings.Repeat("a", 64)
	for _, commands := range [][]string{{"begin", "applied", "stop"}, {"stop"}, {"begin", "begin"}, {"applied"}} {
		s, err := NewGatewaySession(CakeReferenceIPv4LabV1, sha, true)
		if err != nil {
			t.Fatal(err)
		}
		for i, action := range commands {
			err = s.Advance(uint64(i+1), action, sha)
			if commands[len(commands)-1] == "stop" && len(commands) == 3 {
				if err != nil {
					t.Fatal(err)
				}
			} else if i == len(commands)-1 {
				if err == nil || s.Phase() != "failed" {
					t.Fatal("out-of-order command accepted")
				}
			}
		}
		if s.Phase() == "release_requested" && s.Advance(4, "begin", sha) == nil {
			t.Fatal("session reused")
		}
		if s.Advance(1, "begin", sha) == nil {
			t.Fatal("failed session revived")
		}
	}
	for _, tc := range []struct {
		seq uint64
		sha string
	}{{2, sha}, {1, strings.Repeat("b", 64)}} {
		s, _ := NewGatewaySession(CakeReferenceIPv4LabV1, sha, true)
		if s.Advance(tc.seq, "begin", tc.sha) == nil || s.Advance(1, "begin", sha) == nil {
			t.Fatal("binding violation recoverable")
		}
	}
}
