package core

import "fmt"

type CakePlanningScope string

const (
	CakeScopeOwnedIPv4Lab    CakePlanningScope = "owned_ipv4_lab"
	CakeScopeExistingGateway CakePlanningScope = "existing_gateway"
)

// CakePlanningQueue describes a caller's assessment of the whole root profile,
// not just the presence of a qdisc whose kind is "cake".
type CakePlanningQueue string

const (
	CakeQueueUnknown      CakePlanningQueue = "unknown"
	CakeQueueUnconfigured CakePlanningQueue = "unconfigured"
	CakeQueueReference    CakePlanningQueue = "reference_conformant"
	CakeQueueOther        CakePlanningQueue = "other_configuration"
)

// CakePlanningChecks are caller-supplied assumptions for an offline proposal.
// They do not authenticate consent, detect privileges, or attest cleanup.
// LocalConsent is distinct from consent to join a group or share observations.
type CakePlanningChecks struct {
	ReferenceValidated bool
	LocalConsent       bool
	PathValidated      bool
	OwnershipValidated bool
	SupervisionReady   bool
	PermissionsChecked bool
}

type CakePlanningInput struct {
	Scope  CakePlanningScope
	Queue  CakePlanningQueue
	Checks CakePlanningChecks
}

type CakePlanningDecision string

const (
	CakePlanAbstain          CakePlanningDecision = "abstain"
	CakePlanKeepReference    CakePlanningDecision = "keep_reference"
	CakePlanProposeReference CakePlanningDecision = "propose_reference"
)

type CakeReferenceID string

// CakeReferenceIPv4LabV1 identifies the complete, fixed profile documented in
// STATIC_CAKE_PLANNING.md. Its 4 Mbit/s rate belongs to the synthetic laboratory;
// it is neither a household default nor an estimate of WAN capacity.
const CakeReferenceIPv4LabV1 CakeReferenceID = "cake-ipv4-lab-4mbit-v1"

type CakePlanningReason string

const (
	CakeReasonUnsupportedScope       CakePlanningReason = "scope_not_supported"
	CakeReasonQueueUnknown           CakePlanningReason = "queue_not_assessed"
	CakeReasonOtherConfiguration     CakePlanningReason = "other_configuration_preserved"
	CakeReasonAlreadyReference       CakePlanningReason = "already_reference"
	CakeReasonReferenceUnvalidated   CakePlanningReason = "reference_not_validated"
	CakeReasonConsentUnconfirmed     CakePlanningReason = "local_consent_not_confirmed"
	CakeReasonPathUnvalidated        CakePlanningReason = "path_not_validated"
	CakeReasonOwnershipUnvalidated   CakePlanningReason = "ownership_not_validated"
	CakeReasonSupervisionUnavailable CakePlanningReason = "supervision_not_ready"
	CakeReasonPermissionsUnchecked   CakePlanningReason = "permissions_not_checked"
	CakeReasonPrerequisitesConfirmed CakePlanningReason = "prerequisites_confirmed"
)

// CakePlan is a recommendation, never an executable command or authorization.
// Reference is empty when abstaining. It identifies a profile, not an interface.
type CakePlan struct {
	Decision  CakePlanningDecision
	Reference CakeReferenceID
	Reasons   []CakePlanningReason
}

// PlanStaticCake evaluates supplied assumptions without I/O or mutation.
// An executor must independently recheck fresh observations and local authority;
// this package deliberately supplies no executor or production-ready decision.
func PlanStaticCake(input CakePlanningInput) (CakePlan, error) {
	switch input.Scope {
	case "", CakeScopeOwnedIPv4Lab, CakeScopeExistingGateway:
	default:
		return CakePlan{}, fmt.Errorf("unknown CAKE planning scope: %q", input.Scope)
	}
	switch input.Queue {
	case "", CakeQueueUnknown, CakeQueueUnconfigured, CakeQueueReference, CakeQueueOther:
	default:
		return CakePlan{}, fmt.Errorf("unknown CAKE queue assessment: %q", input.Queue)
	}
	abstain := func(reasons ...CakePlanningReason) CakePlan {
		return CakePlan{Decision: CakePlanAbstain, Reasons: reasons}
	}
	if input.Scope != CakeScopeOwnedIPv4Lab {
		return abstain(CakeReasonUnsupportedScope), nil
	}
	switch input.Queue {
	case "", CakeQueueUnknown:
		return abstain(CakeReasonQueueUnknown), nil
	case CakeQueueOther:
		return abstain(CakeReasonOtherConfiguration), nil
	case CakeQueueReference:
		// Preserving an already assessed reference proposes no modification.
		return CakePlan{Decision: CakePlanKeepReference, Reference: CakeReferenceIPv4LabV1,
			Reasons: []CakePlanningReason{CakeReasonAlreadyReference}}, nil
	}
	checks := input.Checks
	var missing []CakePlanningReason
	for _, check := range []struct {
		confirmed bool
		reason    CakePlanningReason
	}{
		{checks.ReferenceValidated, CakeReasonReferenceUnvalidated},
		{checks.LocalConsent, CakeReasonConsentUnconfirmed},
		{checks.PathValidated, CakeReasonPathUnvalidated},
		{checks.OwnershipValidated, CakeReasonOwnershipUnvalidated},
		{checks.SupervisionReady, CakeReasonSupervisionUnavailable},
		{checks.PermissionsChecked, CakeReasonPermissionsUnchecked},
	} {
		if !check.confirmed {
			missing = append(missing, check.reason)
		}
	}
	if len(missing) != 0 {
		return abstain(missing...), nil
	}
	return CakePlan{Decision: CakePlanProposeReference, Reference: CakeReferenceIPv4LabV1,
		Reasons: []CakePlanningReason{CakeReasonPrerequisitesConfirmed}}, nil
}
