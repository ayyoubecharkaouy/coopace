package linux

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const (
	cakeRateBitsPerSecond  = 4_000_000
	cakeRateBytesPerSecond = 500_000
	cakeRTTUS              = 100_000
	cakeMemoryLimitBytes   = 1_048_576
	cakeOutputLimit        = 64 * 1024
)

// CakeReference is a fresh catalogue snapshot, not an executable authorization.
// A future executor must resolve the ID itself, rather than trust modified fields.
type CakeReference struct {
	ID                core.CakeReferenceID
	Interface         string
	Handle            string
	RateBitsPerSecond uint64
	RTTUS             uint64
	MemoryLimitBytes  uint64
	AddArguments      []string
}

func LookupCakeReference(id core.CakeReferenceID) (CakeReference, error) {
	if id != core.CakeReferenceIPv4LabV1 {
		return CakeReference{}, fmt.Errorf("unknown CAKE reference: %q", id)
	}
	return CakeReference{ID: id, Interface: "wan", Handle: "10:", RateBitsPerSecond: cakeRateBitsPerSecond,
		RTTUS: cakeRTTUS, MemoryLimitBytes: cakeMemoryLimitBytes,
		AddArguments: []string{"qdisc", "add", "dev", "wan", "root", "handle", "10:",
			"cake", "bandwidth", "4mbit", "besteffort", "flows", "nonat", "nowash", "raw",
			"mpu", "0", "rtt", "100ms", "split-gso", "no-ack-filter", "egress", "memlimit", "1048576", "fwmark", "0"}}, nil
}

type CakeProducerProfile string

const CakeIPRoute2V610 CakeProducerProfile = "iproute2-6.1.0"

type CakeProducer struct {
	Profile       CakeProducerProfile
	VersionOutput string
}

var cakeProducerPattern = regexp.MustCompile(`^tc utility, iproute2-6\.1\.0(?:, [^\r\n]+)?$`)

func ParseCakeProducer(data []byte) (CakeProducer, error) {
	if len(data) > 512 {
		return CakeProducer{}, fmt.Errorf("tc version output exceeds 512 bytes")
	}
	for _, value := range data {
		if value > 127 {
			return CakeProducer{}, fmt.Errorf("tc version output must be ASCII")
		}
	}
	text := strings.Trim(string(data), " \t\r\n\v\f\x1c\x1d\x1e\x1f")
	if !cakeProducerPattern.MatchString(text) {
		return CakeProducer{}, fmt.Errorf("unsupported tc producer; iproute2-6.1.0 required")
	}
	return CakeProducer{Profile: CakeIPRoute2V610, VersionOutput: string(data)}, nil
}

// CakeOptions names the units exported by tc, including bytes/s and microseconds.
type CakeOptions struct {
	BandwidthBytesPerSecond uint64
	RTTUS                   uint64
	MemoryLimitBytes        uint64
	Diffserv                string
	FlowMode                string
	NAT                     bool
	Wash                    bool
	Ingress                 bool
	ACKFilter               string
	SplitGSO                bool
	Raw                     bool
	Overhead                uint64
	FWMark                  string
	MPU                     uint64
	ATM                     string
	Autorate                bool
}

type CakeConfiguration struct {
	Profile       CakeProducerProfile
	Effective     CakeOptions
	OmittedFields map[string]string
}
