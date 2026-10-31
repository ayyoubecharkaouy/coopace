package linux

import "testing"

func TestLabNamespaceIdentitiesRequireCurrentRetainedAndExpectedMatch(t *testing.T) {
	target := NetworkNamespaceIdentity{Device: 11, Inode: 21}
	original := NetworkNamespaceIdentity{Device: 11, Inode: 10}
	if err := validateLabNamespaceIdentities(target, target, target, original); err != nil {
		t.Fatal(err)
	}
	for _, values := range [][4]NetworkNamespaceIdentity{
		{{}, target, target, original}, {target, {}, target, original}, {target, target, {}, original}, {target, target, target, {}},
		{target, original, target, original}, {target, target, original, original}, {target, target, target, target},
		{target, {Device: 12, Inode: 21}, target, original},
	} {
		if err := validateLabNamespaceIdentities(values[0], values[1], values[2], values[3]); err == nil {
			t.Fatalf("inconsistent or original namespace accepted: %+v", values)
		}
	}
}
