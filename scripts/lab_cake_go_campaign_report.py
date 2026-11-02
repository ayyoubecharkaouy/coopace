"""In-process campaign verdict after successful supervision; not a native replay."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("report_assessment", Path(__file__).with_name("lab_cake_go_campaign_assess.py"))
assessment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assessment)
spec = importlib.util.spec_from_file_location("report_go", Path(__file__).with_name("lab_cake_go.py"))
go = importlib.util.module_from_spec(spec)
spec.loader.exec_module(go)
protocol = assessment.protocol
require, Error = protocol.require, protocol.Error


def equal(left, right):
    require(json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False),
            "Rapport différent des preuves durables.")


def capture(folder, summary, name, limit):
    require(summary['file'] == name, "Capture de campagne inattendue.")
    raw = go.read(folder / name, limit)
    require(len(raw) <= limit and summary['bytes'] == len(raw) and summary['sha256'] == hashlib.sha256(raw).hexdigest(),
            "Capture de campagne modifiée ou trop grande.")
    return raw


def evidence(report, folder):
    group = report['traffic_group']
    raw = capture(folder, report['supervisor_journal'], 'supervisor.jsonl', 16 * 1024 * 1024)
    rows = [go.protocol.document(line, 16 * 1024 * 1024) for line in raw.splitlines()]
    require(rows and len(rows) <= 100000, "Journal absent ou trop grand.")
    require([r['sequence'] for r in rows] == list(range(1, len(rows) + 1)), "Journal hors séquence.")
    data = [r['data'] for r in rows]
    def one(event):
        found = [i for i, d in enumerate(data) if d.get('event') == event]
        require(len(found) == 1, "Transition absente ou répétée : " + event)
        return found[0]
    require(one('environment_verified') < one('resources_owned') < one('go_phase_finished') < one('path_verified')
            < one('traffic_launch_intent') < one('traffic_group_stopped') < one('combined_evidence_verified') < one('control_complete'),
            "Ordre global des preuves incorrect.")
    equal(data[one('go_phase_finished')]['phase'], report['go_phase'])
    require(data[-1]['event'] == 'control_complete' and data[-1]['cleanup_verified'] is True, "Nettoyage non attesté.")
    require(report['cleanup_verified'] is True and report['path_check']['path_verified'] is True
            and report['path_check']['state'] == 'verified' and report['go_phase']['worker_exit_code'] == 0,
            "Contexte Go/passage/nettoyage incomplet.")
    require(len(report['groups']) == 2 and all(g['state'] == 'stopped' for g in report['groups']), "Groupes non récupérés.")
    crash = report['mode'] == 'check-crash'
    require(group['state'] == ('crash_verified' if crash else 'collected') and group['driver_exit_code'] == (-9 if crash else 0)
            and group['reaped_descendants'] == (3 if crash else 0), "Fin du pilote incompatible.")
    stdout = capture(folder, group['stdout'], 'driver.stdout.bin', protocol.EVENT_BUDGET)
    capture(folder, group['stderr'], 'driver.stderr.bin', 256 * 1024)
    events = [d['message'] for d in data if d.get('event') == 'campaign_driver_event']
    lines = stdout.splitlines(keepends=True)
    equal([protocol.parse_event(line, report['session_id']) for line in lines], events)
    dialogue = protocol.Dialogue(report['session_id'])
    pending = None
    for d in data:
        if d['event'] == 'campaign_driver_event':
            dialogue.event(protocol._wire(d['message']))
        elif d['event'] == 'campaign_control_intent':
            require(pending is None, "Intention répétée sans envoi.")
            pending = d
        elif d['event'] == 'campaign_control_sent':
            require(pending is not None, "Envoi sans intention durable.")
            equal({k:pending[k] for k in ('pair','condition','action')}, {k:d[k] for k in ('pair','condition','action')})
            raw_control = base64.b64decode(pending['frame_base64'], validate=True)
            parsed = protocol.parse_control(raw_control, report['session_id'])
            equal({k:parsed[k] for k in ('pair','condition','action')}, {k:d[k] for k in ('pair','condition','action')})
            dialogue.control(raw_control)
            pending = None
    require(pending is None, "Accusé non envoyé.")
    if crash:
        require(dialogue.phase == (1, 'loaded') and dialogue.state == 'continue', "Panne hors de la frontière contractuelle.")
        require(len(group['phases']) == 2 and group['phases'][1]['state'] == 'interrupted', "Phase interrompue absente.")
    else:
        dialogue.finish_controls(); dialogue.finish_events()
        require(dialogue.complete and len(group['phases']) == 6, "Dialogue de campagne incomplet.")
    for phase in group['phases']:
        pair, condition = phase['pair'], phase['condition']
        scoped = [d for d in data if d.get('pair') == pair and d.get('condition') == condition]
        def phase_one(event):
            values = [d for d in scoped if d['event'] == event]
            require(len(values) == 1, "Preuve de phase absente ou répétée : " + event)
            return values[0]
        equal(phase['helpers'], phase_one('campaign_helpers_verified')['helpers'])
        equal(phase['samples'], [d['reading'] for d in data if d['event'] == 'campaign_sample'
                               and d['reading']['pair'] == pair and d['reading']['condition'] == condition])
        if phase['state'] == 'interrupted':
            continue
        end = phase_one('phase_end_observed')['observed_monotonic_ns']
        equal(end, phase['end_observed_monotonic_ns'])
        end_message = [v for v in events if v['event'] == 'end' and v['pair'] == pair and v['condition'] == condition]
        require(len(end_message) == 1, "Résultat de phase absent.")
        equal(end_message[0]['result'], phase['result'])
        end_raw = [line for line in lines if protocol.parse_event(line, report['session_id']) == end_message[0]]
        require(len(end_raw) == 1 and hashlib.sha256(end_raw[0]).hexdigest() == phase_one('phase_end_observed')['line_sha256'], 'Observation de fin différente de la capture.')
        stopped = phase_one('campaign_helpers_stopped')['helpers']
        equal(stopped, phase['helpers_stopped'])
        require(len(stopped) == len(phase['helpers']) and all(s['pid'] == h['pid'] and s['previous_start_ticks'] == h['start_ticks']
                and (s['reason'] == 'absent' or s['reason'] == 'pid_reused' and s['current_start_ticks'] != h['start_ticks'])
                for s,h in zip(stopped,phase['helpers'])), "Arrêt des outils non confirmé.")
        drains = [s for s in phase['samples'] if s['phase'] == 'drain']
        require(len(drains) >= 2 and all(type(s['read_finished_monotonic_ns']) is int for s in drains), "Vidage absent.")
        last = drains[-1]
        empty = [s for s in drains if s['statistics']['backlog_bytes'] == s['statistics']['queued_packets'] == 0]
        first_empty = None
        for sample in drains:
            if sample in empty:
                first_empty = sample if first_empty is None else first_empty
            else:
                first_empty = None
        require(first_empty is not None and len(empty) >= 2 and empty[-1] == last
                and last['read_finished_monotonic_ns']-first_empty['read_finished_monotonic_ns'] >= 500_000_000,
                "Double lecture vide non confirmée.")
        advance = [d for d in scoped if d['event'] == 'campaign_control_sent' and d['action'] == 'advance']
        require(len(advance) == 1 and end <= last['read_finished_monotonic_ns'] <= advance[0]['sent_monotonic_ns'] < end + 3_000_000_000,
                "Vidage ou autorisation tardive.")
    return crash


def finalize(report, folder, *, operational_success):
    """Called by the owner after closed captures/journal, before exclusive save."""
    report.update(kind='lab_cake_go_campaign', technical_valid=False, load_scenario='non_exploitable', connections='not_assessed',
                  comparison='not_assessed', coopace_benefit='not_assessed', phases=(report.get('traffic_group') or {}).get('phases', []),
                  assessment=None)
    if not operational_success:
        return
    try:
        crash = evidence(report, folder)
        result = assessment.assess(report['phases'], crash=crash)
        report['assessment'] = result
        require(crash or result['measurements_valid'] is True, 'Mesures de campagne inexploitables : ' + '; '.join(result['reasons']))
        report.update(technical_valid=None if crash else True, load_scenario=result['load_scenario'], connections=result['connections'])
    except Exception:
        report.update(technical_valid=False, load_scenario='non_exploitable', connections='not_assessed')
        raise
