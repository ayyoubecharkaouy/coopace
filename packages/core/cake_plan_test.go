package core_test

import (
	"fmt"
	"reflect"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func labCakeInput() core.CakePlanningInput {
	return core.CakePlanningInput{
		Scope: core.CakeScopeOwnedIPv4Lab,
		Queue: core.CakeQueueUnconfigured,
		Checks: core.CakePlanningChecks{
			ReferenceValidated: true, LocalConsent: true, PathValidated: true,
			OwnershipValidated: true, SupervisionReady: true, PermissionsChecked: true,
		},
	}
}

func TestStaticCakePlanningProposesOnlyTheNamedLaboratoryReference(t *testing.T) {
	input := labCakeInput()
	plan, err := core.PlanStaticCake(input)
	if err != nil || plan.Decision != core.CakePlanProposeReference || plan.Reference != core.CakeReferenceIPv4LabV1 {
		t.Fatalf("unexpected laboratory proposal: %+v, %v", plan, err)
	}
	if !reflect.DeepEqual(input, labCakeInput()) {
		t.Fatal("planning changed caller assumptions")
	}
	if !reflect.DeepEqual(plan.Reasons, []core.CakePlanningReason{core.CakeReasonPrerequisitesConfirmed}) {
		t.Fatalf("unexpected proposal explanation: %v", plan.Reasons)
	}
}

func TestStaticCakePlanningRequiresEveryAssumptionForAChange(t *testing.T) {
	tests := []struct {
		name   string
		remove func(*core.CakePlanningChecks)
		reason core.CakePlanningReason
	}{
		{"reference", func(c *core.CakePlanningChecks) { c.ReferenceValidated = false }, core.CakeReasonReferenceUnvalidated},
		{"local consent", func(c *core.CakePlanningChecks) { c.LocalConsent = false }, core.CakeReasonConsentUnconfirmed},
		{"traffic path", func(c *core.CakePlanningChecks) { c.PathValidated = false }, core.CakeReasonPathUnvalidated},
		{"ownership", func(c *core.CakePlanningChecks) { c.OwnershipValidated = false }, core.CakeReasonOwnershipUnvalidated},
		{"supervision", func(c *core.CakePlanningChecks) { c.SupervisionReady = false }, core.CakeReasonSupervisionUnavailable},
		{"permissions", func(c *core.CakePlanningChecks) { c.PermissionsChecked = false }, core.CakeReasonPermissionsUnchecked},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			input := labCakeInput()
			tt.remove(&input.Checks)
			plan, err := core.PlanStaticCake(input)
			if err != nil || plan.Decision != core.CakePlanAbstain || plan.Reference != "" ||
				!reflect.DeepEqual(plan.Reasons, []core.CakePlanningReason{tt.reason}) {
				t.Fatalf("missing prerequisite accepted or misreported: %+v, %v", plan, err)
			}
		})
	}
}

func TestStaticCakePlanningDefaultsAndMissingReasonsRemainExplicit(t *testing.T) {
	plan, err := core.PlanStaticCake(core.CakePlanningInput{})
	if err != nil || plan.Decision != core.CakePlanAbstain || plan.Reference != "" ||
		!reflect.DeepEqual(plan.Reasons, []core.CakePlanningReason{core.CakeReasonUnsupportedScope}) {
		t.Fatalf("zero input proposed a change: %+v, %v", plan, err)
	}
	input := labCakeInput()
	input.Checks = core.CakePlanningChecks{}
	plan, err = core.PlanStaticCake(input)
	want := []core.CakePlanningReason{core.CakeReasonReferenceUnvalidated, core.CakeReasonConsentUnconfirmed,
		core.CakeReasonPathUnvalidated, core.CakeReasonOwnershipUnvalidated,
		core.CakeReasonSupervisionUnavailable, core.CakeReasonPermissionsUnchecked}
	if err != nil || plan.Decision != core.CakePlanAbstain || plan.Reference != "" || !reflect.DeepEqual(plan.Reasons, want) {
		t.Fatalf("missing assumptions were lost or reordered: %+v, %v", plan, err)
	}
	plan.Reasons[0] = "caller changed its result"
	again, err := core.PlanStaticCake(input)
	if err != nil || !reflect.DeepEqual(again.Reasons, want) {
		t.Fatalf("one result contaminated another evaluation: %+v, %v", again, err)
	}
}

func TestStaticCakePlanningNeverProposesForUnknownOrExistingGatewayScope(t *testing.T) {
	for _, scope := range []core.CakePlanningScope{"", core.CakeScopeExistingGateway} {
		for _, queue := range []core.CakePlanningQueue{core.CakeQueueUnknown, core.CakeQueueUnconfigured, core.CakeQueueReference, core.CakeQueueOther} {
			input := labCakeInput()
			input.Scope, input.Queue = scope, queue
			plan, err := core.PlanStaticCake(input)
			if err != nil || plan.Decision != core.CakePlanAbstain || plan.Reference != "" {
				t.Fatalf("unsupported scope passed using queue state: %+v, %+v, %v", input, plan, err)
			}
		}
	}
}

func TestStaticCakePlanningPreservesUnknownAndOtherConfigurations(t *testing.T) {
	for _, entry := range []struct {
		queue  core.CakePlanningQueue
		reason core.CakePlanningReason
	}{{"", core.CakeReasonQueueUnknown}, {core.CakeQueueUnknown, core.CakeReasonQueueUnknown},
		{core.CakeQueueOther, core.CakeReasonOtherConfiguration}} {
		input := labCakeInput()
		input.Queue = entry.queue
		plan, err := core.PlanStaticCake(input)
		if err != nil || plan.Decision != core.CakePlanAbstain || plan.Reference != "" ||
			!reflect.DeepEqual(plan.Reasons, []core.CakePlanningReason{entry.reason}) {
			t.Fatalf("unknown/other queue was replaced: %+v, %v", plan, err)
		}
	}
}

func TestStaticCakePlanningKeepsConformantReferenceWithoutNewModification(t *testing.T) {
	input := core.CakePlanningInput{Scope: core.CakeScopeOwnedIPv4Lab, Queue: core.CakeQueueReference}
	plan, err := core.PlanStaticCake(input)
	if err != nil || plan.Decision != core.CakePlanKeepReference || plan.Reference != core.CakeReferenceIPv4LabV1 ||
		!reflect.DeepEqual(plan.Reasons, []core.CakePlanningReason{core.CakeReasonAlreadyReference}) {
		t.Fatalf("conformant reference requested another change: %+v, %v", plan, err)
	}
}

func TestStaticCakePlanningRejectsUnknownEnumsBeforeAnyRecommendation(t *testing.T) {
	for _, input := range []core.CakePlanningInput{
		{Scope: "new_scope", Queue: core.CakeQueueReference},
		{Scope: core.CakeScopeOwnedIPv4Lab, Queue: "almost_cake"},
		{Scope: core.CakeScopeExistingGateway, Queue: "almost_cake"},
	} {
		plan, err := core.PlanStaticCake(input)
		if err == nil || !reflect.DeepEqual(plan, core.CakePlan{}) {
			t.Fatalf("unknown input accepted: %+v -> %+v, %v", input, plan, err)
		}
	}
}

func ExamplePlanStaticCake() {
	input := core.CakePlanningInput{Scope: core.CakeScopeOwnedIPv4Lab, Queue: core.CakeQueueUnconfigured}
	plan, _ := core.PlanStaticCake(input)
	fmt.Println(plan.Decision, len(plan.Reasons))
	input.Checks = core.CakePlanningChecks{
		ReferenceValidated: true, LocalConsent: true, PathValidated: true,
		OwnershipValidated: true, SupervisionReady: true, PermissionsChecked: true,
	}
	plan, _ = core.PlanStaticCake(input)
	fmt.Println(plan.Decision, plan.Reference)
	// Output:
	// abstain 6
	// propose_reference cake-ipv4-lab-4mbit-v1
}
