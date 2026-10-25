package latency

import (
	"bytes"
	"encoding/json"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestJSONUsesMillisecondsAndExplicitMissingValues(t *testing.T) {
	for _, sample := range []core.LatencySample{{Duration: 1500 * time.Microsecond}, {Failure: core.LatencyTimeout}} {
		summary, err := core.SummarizeLatency([]core.LatencySample{sample})
		if err != nil {
			t.Fatal(err)
		}
		report := Report{Options: validOptions(), Attempts: []Attempt{{Sample: sample}}, Summary: summary}
		var output bytes.Buffer
		if err := WriteJSON(&output, report, "test-version"); err != nil {
			t.Fatal(err)
		}
		var data jsonReport
		if err := json.Unmarshal(output.Bytes(), &data); err != nil {
			t.Fatal(err)
		}
		if data.SchemaVersion != 1 || data.Method != "tcp_connect" || data.Version != "test-version" || data.GoVersion == "" || data.Target != report.Options.Target {
			t.Fatalf("missing report provenance: %+v", data)
		}
		if sample.Failure != "" {
			if data.ConnectMS != nil || data.Attempts[0].ConnectMS != nil || data.Attempts[0].Failure != sample.Failure {
				t.Fatal("failed attempt received fabricated latency values")
			}
		} else if data.ConnectMS == nil || data.Attempts[0].ConnectMS == nil || *data.Attempts[0].ConnectMS != 1.5 || data.ConnectMS.P50 != 1.5 {
			t.Fatalf("wrong latency units: %+v", data)
		}
	}
}
