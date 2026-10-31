package labcontrol

import (
	"fmt"
	"io"
	"os"
	"time"

	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

const (
	WorkerLifetime  = 30 * time.Second
	BoundaryTimeout = 5 * time.Second
)

type Phase string

const (
	NeedBinding   Phase = "need_binding"
	Bound         Phase = "bound"
	WaitingApply  Phase = "waiting_apply"
	Applying      Phase = "applying"
	WaitingFinish Phase = "waiting_finish"
	Finished      Phase = "finished"
	Failed        Phase = "failed"
)

// Session tracks protocol progress, not kernel mutations or authorization. It
// is used sequentially by one future worker; callers must not use it concurrently.
type Session struct {
	request            Request
	phase              Phase
	deadline           time.Time
	boundary           time.Time
	now                func() time.Time
	verify             func(linux.NetworkNamespaceIdentity, *os.File, *os.File) error
	retained, original *os.File
	failure            error
}

// started must be captured by the trusted worker before reading initialization,
// using time.Now so deadline comparisons retain Go's monotonic component.
func NewSession(request Request, expectedSession string, started time.Time) (*Session, error) {
	return newSession(request, expectedSession, started, time.Now)
}

func newSession(request Request, expectedSession string, started time.Time, now func() time.Time) (*Session, error) {
	if !request.valid || !validSession(expectedSession) || request.session != expectedSession {
		return nil, fmt.Errorf("request does not match the trusted laboratory session")
	}
	if started.IsZero() || started.After(now()) {
		return nil, fmt.Errorf("invalid worker start time")
	}
	s := &Session{request: request, phase: NeedBinding, deadline: started.Add(WorkerLifetime),
		boundary: started.Add(BoundaryTimeout), now: now, verify: linux.VerifyLabNamespace}
	if err := s.Check(); err != nil {
		return nil, err
	}
	return s, nil
}

func (s *Session) Phase() Phase { return s.phase }

func (s *Session) Abort(cause error) error {
	if s.phase == Failed {
		return s.failure
	}
	if cause == nil {
		cause = fmt.Errorf("laboratory session aborted")
	}
	s.phase, s.failure = Failed, cause
	return cause
}

func (s *Session) Check() error {
	if s.now == nil || s.verify == nil || !s.request.valid {
		return s.Abort(fmt.Errorf("laboratory session is not initialized"))
	}
	if s.phase == Failed {
		return s.failure
	}
	if s.phase == Finished {
		return nil
	}
	now := s.now()
	if !now.Before(s.deadline) {
		return s.Abort(fmt.Errorf("worker lifetime exceeded"))
	}
	if !now.Before(s.boundary) {
		return s.Abort(fmt.Errorf("laboratory protocol boundary timed out"))
	}
	return nil
}

func (s *Session) expect(phase Phase) error {
	if err := s.Check(); err != nil {
		return err
	}
	if s.phase != phase {
		return s.Abort(fmt.Errorf("unexpected laboratory transition from %s", s.phase))
	}
	return nil
}

func (s *Session) advance(phase Phase) {
	s.phase = phase
	s.boundary = s.now().Add(BoundaryTimeout)
	if s.boundary.After(s.deadline) {
		s.boundary = s.deadline
	}
}

func (s *Session) verifyBinding() error {
	if err := s.verify(s.request.namespace, s.retained, s.original); err != nil {
		return s.Abort(err)
	}
	return s.Check()
}

// BindNamespace borrows descriptors. Their lifetime remains owned by the caller.
func (s *Session) BindNamespace(retained, original *os.File) error {
	if err := s.expect(NeedBinding); err != nil {
		return err
	}
	s.retained, s.original = retained, original
	if err := s.verifyBinding(); err != nil {
		return err
	}
	s.advance(Bound)
	return nil
}

// Ready checks the initial dump. The driver emits the event; live interface
// and DOWN checks belong to the native tool backend.
func (s *Session) Ready(initial []byte) error {
	if err := s.expect(Bound); err != nil {
		return err
	}
	if err := s.verifyBinding(); err != nil {
		return err
	}
	if err := linux.ValidateCakeInitial(initial); err != nil {
		return s.Abort(err)
	}
	if err := s.Check(); err != nil {
		return err
	}
	s.advance(WaitingApply)
	return nil
}

func (s *Session) Accept(command Command) error {
	if err := s.Check(); err != nil {
		return err
	}
	if command.session != s.request.session {
		return s.Abort(fmt.Errorf("control refers to another session"))
	}
	var next Phase
	switch {
	case s.phase == WaitingApply && command.action == "apply":
		next = Applying
	case s.phase == WaitingFinish && command.action == "finish":
		next = Finished
	default:
		return s.Abort(fmt.Errorf("duplicate or out-of-order laboratory control"))
	}
	if err := s.verifyBinding(); err != nil {
		return err
	}
	s.advance(next)
	return nil
}

// Receive makes malformed frames and EOF terminal. It does not supply transport
// deadlines for a reader blocked in I/O; WorkerTransport supplies those for
// inherited Linux pipes.
func (s *Session) Receive(input io.Reader) error {
	if err := s.Check(); err != nil {
		return err
	}
	if s.phase != WaitingApply && s.phase != WaitingFinish {
		return s.Abort(fmt.Errorf("control received before readiness"))
	}
	command, err := ReadCommand(input)
	if err != nil {
		return s.Abort(err)
	}
	return s.Accept(command)
}

// Applied validates supplied qdisc data; it does not run tc or prove the origin
// of that data. The future trusted worker must collect it after the actual add.
func (s *Session) Applied(data []byte, profile linux.CakeProducerProfile) (linux.CakeReading, error) {
	if err := s.expect(Applying); err != nil {
		return linux.CakeReading{}, err
	}
	if err := s.verifyBinding(); err != nil {
		return linux.CakeReading{}, err
	}
	reading, err := linux.ParseCakeReading(data, profile)
	if err != nil {
		return linux.CakeReading{}, s.Abort(err)
	}
	if err := s.Check(); err != nil {
		return linux.CakeReading{}, err
	}
	s.advance(WaitingFinish)
	return reading, nil
}
