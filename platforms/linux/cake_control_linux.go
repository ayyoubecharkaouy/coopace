//go:build linux && !android

package linux

import (
	"context"
	"errors"
	"fmt"
	"os"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

// CakeLabLaunch borrows namespace FDs owned by the worker transport. The caller
// must establish local authority and fresh-resource ownership independently.
type CakeLabLaunch struct {
	IP, TC           LabToolSpec
	Namespace        NetworkNamespaceIdentity
	Target, Original *os.File
	Observer         LabToolObserver
}

// LabCakeControl is a sequential, one-shot adapter for the fixed DOWN lab
// profile. It does not enter namespaces, activate links or remove resources.
type LabCakeControl struct {
	launch       CakeLabLaunch
	verify       func(NetworkNamespaceIdentity, *os.File, *os.File) error
	state        string
	failure      error
	producer     CakeProducer
	link         *CakeLabLink
	addAttempted bool
	calls        []LabToolCall
}

// NewLabCakeControl validates launch parameters without executing a tool. Every
// operation uses the native namespace verifier; no caller-provided bypass exists.
func NewLabCakeControl(launch CakeLabLaunch) (*LabCakeControl, error) {
	return newLabCakeControl(launch, VerifyLabNamespace)
}

func newLabCakeControl(launch CakeLabLaunch, verify func(NetworkNamespaceIdentity, *os.File, *os.File) error) (*LabCakeControl, error) {
	for _, spec := range []LabToolSpec{launch.IP, launch.TC} {
		if err := spec.Validate(); err != nil {
			return nil, err
		}
	}
	if launch.Namespace.Inode == 0 || launch.Target == nil || launch.Original == nil || verify == nil {
		return nil, fmt.Errorf("laboratory namespace descriptors and identity are required")
	}
	return &LabCakeControl{launch: launch, verify: verify, state: "new"}, nil
}

func (c *LabCakeControl) fail(err error) error {
	if c.failure != nil {
		return c.failure
	}
	c.state, c.failure = "failed", err
	return err
}

func (c *LabCakeControl) expect(state string) error {
	if c.failure != nil {
		return c.failure
	}
	if c.state != state {
		return c.fail(fmt.Errorf("unexpected CAKE backend phase %s", c.state))
	}
	return nil
}

func (c *LabCakeControl) binding(ctx context.Context) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := c.verify(c.launch.Namespace, c.launch.Target, c.launch.Original); err != nil {
		return err
	}
	return ctx.Err()
}

func (c *LabCakeControl) run(ctx context.Context, spec LabToolSpec, args []string, limit int) ([]byte, error) {
	if err := c.binding(ctx); err != nil {
		return nil, err
	}
	if c.launch.Observer != nil {
		if err := c.launch.Observer.ToolIntent(spec, append([]string(nil), args...)); err != nil {
			return nil, err
		}
	}
	if err := c.binding(ctx); err != nil {
		return nil, err
	}
	call, err := runCakeTool(ctx, spec, args, limit)
	c.calls = append(c.calls, call)
	if c.launch.Observer != nil {
		err = errors.Join(err, c.launch.Observer.ToolResult(cloneLabToolCall(call)))
	}
	if err != nil {
		return nil, err
	}
	return call.Stdout, nil
}

func (c *LabCakeControl) checkLink(ctx context.Context) error {
	raw, err := c.run(ctx, c.launch.IP, []string{"-j", "-d", "link", "show"}, cakeOutputLimit)
	if err != nil {
		return err
	}
	link, err := cakeLabLinks(raw)
	if err != nil {
		return err
	}
	if c.link != nil && *c.link != link {
		return fmt.Errorf("laboratory veth identity changed")
	}
	raw, err = c.run(ctx, c.launch.IP, []string{"-j", "address", "show", "dev", "wan"}, cakeOutputLimit)
	if err != nil {
		return err
	}
	if err := cakeLabAddresses(raw, link); err != nil {
		return err
	}
	if c.link == nil {
		c.link = &link
	}
	return nil
}

func (c *LabCakeControl) qdisc(ctx context.Context) ([]byte, error) {
	return c.run(ctx, c.launch.TC, []string{"-j", "-s", "-r", "qdisc", "show", "dev", "wan"}, cakeOutputLimit)
}

// Prepare checks the producer, DOWN link and initial qdisc without mutation.
func (c *LabCakeControl) Prepare(ctx context.Context) ([]byte, error) {
	if err := c.expect("new"); err != nil {
		return nil, err
	}
	raw, err := c.run(ctx, c.launch.TC, []string{"-V"}, 512)
	if err != nil {
		return nil, c.fail(err)
	}
	c.producer, err = ParseCakeProducer(raw)
	if err != nil {
		return nil, c.fail(err)
	}
	if err := c.checkLink(ctx); err != nil {
		return nil, c.fail(err)
	}
	raw, err = c.qdisc(ctx)
	if err != nil {
		return nil, c.fail(err)
	}
	if err := ValidateCakeInitial(raw); err != nil {
		return nil, c.fail(err)
	}
	if err := c.binding(ctx); err != nil {
		return nil, c.fail(err)
	}
	c.state = "prepared"
	return append([]byte(nil), raw...), nil
}

// Apply is called only after the application's explicit session instruction.
// It performs at most one fixed add, then validates the live reading.
func (c *LabCakeControl) Apply(ctx context.Context) ([]byte, CakeProducerProfile, error) {
	if err := c.expect("prepared"); err != nil {
		return nil, "", err
	}
	c.state = "applying" // Any failure, even preflight, prohibits a second attempt.
	if err := c.checkLink(ctx); err != nil {
		return nil, "", c.fail(err)
	}
	raw, err := c.qdisc(ctx)
	if err != nil {
		return nil, "", c.fail(err)
	}
	if err := ValidateCakeInitial(raw); err != nil {
		return nil, "", c.fail(err)
	}
	reference, err := LookupCakeReference(core.CakeReferenceIPv4LabV1)
	if err != nil {
		return nil, "", c.fail(err)
	}
	if err := c.binding(ctx); err != nil {
		return nil, "", c.fail(err)
	}
	c.addAttempted = true // An error may still have modified the owned qdisc.
	if _, err := c.run(ctx, c.launch.TC, reference.AddArguments, cakeOutputLimit); err != nil {
		return nil, "", c.fail(err)
	}
	raw, err = c.readApplied(ctx)
	if err != nil {
		return nil, "", c.fail(err)
	}
	c.state = "applied"
	return append([]byte(nil), raw...), c.producer.Profile, nil
}

func (c *LabCakeControl) readApplied(ctx context.Context) ([]byte, error) {
	if err := c.checkLink(ctx); err != nil {
		return nil, err
	}
	raw, err := c.qdisc(ctx)
	if err != nil {
		return nil, err
	}
	if _, err := ParseCakeReading(raw, c.producer.Profile); err != nil {
		return nil, err
	}
	if err := c.binding(ctx); err != nil {
		return nil, err
	}
	return raw, nil
}

// Final rechecks the link and qdisc. Resource removal belongs to the supervisor.
func (c *LabCakeControl) Final(ctx context.Context) ([]byte, error) {
	if err := c.expect("applied"); err != nil {
		return nil, err
	}
	raw, err := c.readApplied(ctx)
	if err != nil {
		return nil, c.fail(err)
	}
	c.state = "finished"
	return append([]byte(nil), raw...), nil
}

// Evidence returns an independent copy, including partial and failed calls.
func (c *LabCakeControl) Evidence() CakeLabEvidence {
	result := CakeLabEvidence{State: c.state, Producer: c.producer, AddAttempted: c.addAttempted}
	if c.failure != nil {
		result.Error = c.failure.Error()
	}
	if c.link != nil {
		link := *c.link
		result.Link = &link
	}
	for _, call := range c.calls {
		result.Calls = append(result.Calls, cloneLabToolCall(call))
	}
	return result
}
