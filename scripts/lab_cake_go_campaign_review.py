"""Offline replay of campaign phase evidence only; no native certification."""

import hashlib
import importlib.util
from pathlib import Path


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = sibling('phase_review_common', 'lab_cake_go_active_review.py')
assessment = sibling('phase_review_metrics', 'lab_cake_go_campaign_assess.py')
wire = assessment.protocol
go, require, equal, Error = base.go, base.require, base.equal, base.Error


def sealed(folder, name, summary, limit):
    require(summary['file'] == name and type(summary['bytes']) is int, 'Capture inattendue.')
    raw = go.read(folder / name, limit)
    equal(summary, {'file': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}, 'Capture modifiée.')
    return raw


def integer(value):
    require(type(value) is int and value >= 0, 'Temps monotone entier requis.')
    return value


def _replay(folder, report, tools, owned):
    require(report['kind'] == 'lab_cake_go_campaign' and report['mode'] in ('run', 'check-crash'), 'Type ou mode incompatible.')
    session = wire.session_id(report['session_id'])
    names = [f'cg-{session}-{role}' for role in ('c', 'g', 's')]
    require([v[0] for v in owned] == names and len(owned) == 3
            and all(len(v[1]) == 2 and all(type(n) is int and n > 0 for n in v[1]) for v in owned), 'Identités possédées invalides.')
    group, crash = report['traffic_group'], report['mode'] == 'check-crash'
    require(type(group['driver_pid']) is int and group['driver_pid'] > 0, 'Leader de campagne invalide.')
    raw = sealed(folder, 'supervisor.jsonl', report['supervisor_journal'], 16 * 1024 * 1024)
    require(raw.endswith(b'\n'), 'Journal tronqué.')
    rows = [go.protocol.document(line, 16 * 1024 * 1024) for line in raw.splitlines()]
    previous = -1
    for index, row in enumerate(rows, 1):
        require(set(row) == {'schema_version','kind','sequence','recorded_at','elapsed_ns','data'}
                and type(row['schema_version']) is int and row['schema_version'] == 1
                and row['kind'] == 'lab_cake_go_active_journal' and type(row['sequence']) is int and row['sequence'] == index
                and integer(row['elapsed_ns']) >= previous, 'Enveloppe du journal invalide.')
        go.protocol.timestamp(row['recorded_at'])
        previous = row['elapsed_ns']
    require(rows and previous < 190_000_000_000, 'Durée globale incompatible.')
    data = [row['data'] for row in rows]
    output = sealed(folder, 'driver.stdout.bin', group['stdout'], wire.EVENT_BUDGET)
    sealed(folder, 'driver.stderr.bin', group['stderr'], 256 * 1024)
    reader = wire.LineReader(session, 'events')
    messages = reader.feed(output); reader.finish()
    equal(messages, [d['message'] for d in data if d['event'] == 'campaign_driver_event'], 'Dialogue différent de stdout.')
    lines = output.splitlines(keepends=True)
    dialogue, pending, controls = wire.Dialogue(session), None, []
    for index, d in enumerate(data):
        if d['event'] == 'campaign_driver_event':
            dialogue.event(wire._wire(d['message']))
        elif d['event'] == 'campaign_control_intent':
            require(pending is None, 'Intention répétée avant envoi.')
            pending = (index, d)
        elif d['event'] == 'campaign_control_sent':
            require(pending is not None, 'Envoi sans intention.')
            raw_control = go.protocol.source_bytes(pending[1]['frame_base64'], wire.FRAME_LIMIT)
            control = dialogue.control(raw_control)
            for key in ('pair', 'condition', 'action'):
                equal(control[key], pending[1][key], 'Intention différente de la trame.')
                equal(control[key], d[key], 'Envoi différent de la trame.')
            controls.append((pending[0], index, control, integer(d['sent_monotonic_ns'])))
            pending = None
    require(pending is None, 'Accusé incomplet.')
    if crash:
        require(dialogue.phase == (1, 'loaded') and dialogue.state == 'continue', 'Panne hors de la première disponibilité chargée.')
    else:
        dialogue.finish_controls(); dialogue.finish_events()
        require(dialogue.complete, 'Dialogue incomplet.')
    phases = group['phases']
    require(len(phases) == (2 if crash else 6), 'Nombre de phases incompatible.')
    if 'phases' in report:equal(report['phases'], phases, 'Phases racine différentes.')
    # Reparse raw tc bytes; a rewritten normalized sample is not sufficient.
    show = [tools['ip']['path'], 'netns', 'exec', names[1], tools['tc']['path'], '-j', '-s', '-r', 'qdisc', 'show', 'dev', 'wan']
    latest_raw, latest_reading, statistics, samples = None, None, [], []
    for index, d in enumerate(data):
        if d['event'] == 'activation_tool_result' and 'qdisc' in d['arguments']:
            require(d['arguments'] == show and index > 0 and data[index-1]['event'] == 'activation_tool_intent'
                    and data[index-1]['arguments'] == show and d['error'] == ''
                    and integer(d['duration_ns']) < 2_200_000_000, 'Commande CAKE non conforme.')
            latest_raw = go.protocol.source_bytes(d['stdout_base64'], 65536)
        elif d['event'] == 'activation_qdisc':
            require(latest_raw is not None, 'Lecture CAKE sans sortie brute.')
            latest_reading = d['reading']
            equal(latest_reading['qdiscs'], base.collect.cake.queue.document(latest_raw), 'CAKE différent des octets.')
            stats = base.reading(latest_reading)
            if statistics:require(base.collect.cake.queue.statistics_delta(statistics[-1], stats)['available'], 'Compteur CAKE en baisse.')
            statistics.append(stats)
            latest_raw = None
        elif d['event'] == 'campaign_sample':
            value = d['reading']
            require((value['pair'] is None and value['condition'] is None)
                    or type(value['pair']) is int and value['pair'] in (1,2,3) and value['condition'] in ('idle','loaded'), 'Contexte de relevé invalide.')
            equal({k:v for k,v in value.items() if k not in ('phase','pair','condition','read_started_monotonic_ns','read_finished_monotonic_ns')},
                  latest_reading, 'Échantillon sans lecture brute correspondante.')
            require(integer(value['read_started_monotonic_ns']) <= integer(value['read_finished_monotonic_ns']), 'Lecture monotone inversée.')
            samples.append(value)
            latest_reading = None
    require(1 < len(samples) <= 720 and sum(len(base.json.dumps(s, ensure_ascii=False, allow_nan=False).encode()) for s in samples) <= 4 * 1024 * 1024, 'Collecte hors budget.')
    equal(samples, group['queue_samples'], 'Collecte différente du groupe.')
    pids = []
    for phase_index, phase in enumerate(phases):
        pair, condition = wire.PHASES[phase_index]
        require(type(phase['pair']) is int and (phase['pair'],phase['condition']) == (pair,condition), 'Phase hors ordre.')
        scoped = [(i,d) for i,d in enumerate(data) if d.get('pair') == pair and d.get('condition') == condition]
        def one(event):
            found = [(i,d) for i,d in scoped if d['event'] == event]
            require(len(found) == 1, 'Preuve de phase absente ou répétée : '+event)
            return found[0]
        def message(event):
            found = [(i,d['message']) for i,d in enumerate(data) if d['event'] == 'campaign_driver_event'
                     and d['message'].get('pair') == pair and d['message'].get('condition') == condition and d['message']['event'] == event]
            require(len(found) == 1, 'Événement de phase absent ou répété.')
            return found[0]
        acks = {action:[c for c in controls if c[2]['pair'] == pair and c[2]['condition'] == condition and c[2]['action'] == action]
                for action in ('start','continue','advance')}
        begin, _ = message('begin'); ready_at, ready = message('ready'); verified, helpers = one('campaign_helpers_verified')
        require(len(acks['start']) == 1, 'Start absent.')
        start = acks['start'][0]
        require(begin < start[0] < start[1] < ready_at < verified, 'Disponibilité hors ordre.')
        require(rows[ready_at]['elapsed_ns']-rows[start[1]]['elapsed_ns'] < 15_000_000_000, 'Disponibilité hors délai conservateur.')
        equal(helpers['helpers'], phase['helpers'], 'Identités différentes du rapport.')
        require(len(phase['helpers']) == len(ready['helper_pids']), 'Identités incomplètes.')
        equal(ready['helper_pids'], [h['pid'] for h in phase['helpers']], 'PID différents de ready.')
        for i, (pid, helper, args) in enumerate(zip(ready['helper_pids'], phase['helpers'], base.collect.expected_helpers(tools))):
            base.collect.validate_helper(helper, pid, group['driver_pid'], owned[2 if i < 2 else 0][1], tools['target' if i == 0 else 'load'], args)
            pids.append(pid)
        phase_samples = [s for s in samples if s['pair'] == pair and s['condition'] == condition]
        equal(phase_samples, phase['samples'], 'Relevés de phase différents.')
        anchored = [(i,d['reading']) for i,d in enumerate(data) if d['event'] == 'campaign_sample' and d['reading'] in phase_samples]
        require(anchored and begin < anchored[0][0] < start[0] and anchored[0][1]['phase'] == 'before_start'
                and anchored[0][1]['read_finished_monotonic_ns'] <= start[3]
                and sum(s['phase'] == 'before_start' for s in phase_samples) == 1, 'Relevé initial hors frontière.')
        interrupted = crash and phase_index == 1
        if interrupted:
            kills = [(i,d) for i,d in enumerate(data) if d['event'] == 'traffic_kill_intent']
            require(len(kills) == 1, 'Intention de panne absente ou répétée.')
            kill_at, kill = kills[0]
            require(phase['state'] == 'interrupted' and phase['result'] is None and verified < kill_at
                    and kill['driver_pid'] == group['driver_pid'] and not acks['continue'] and not acks['advance'], 'Panne incompatible.')
            continue
        require(phase['state'] == 'complete' and len(acks['continue']) == len(acks['advance']) == 1, 'Phase non clôturée.')
        proceed, advance = acks['continue'][0], acks['advance'][0]
        observed_at, observed = one('phase_end_observed'); ended_at, ended = message('end')
        stopped_at, stopped = one('campaign_helpers_stopped'); collected_at, collected = one('campaign_phase_collected')
        require(verified < proceed[0] < proceed[1] < observed_at < ended_at < stopped_at < collected_at < advance[0] < advance[1], 'Frontières de phase hors ordre.')
        equal(ended['result'], phase['result'], 'Résultat différent de la capture.')
        raw_end = [line for line in lines if wire.parse_event(line, session) == ended]
        require(len(raw_end) == 1 and hashlib.sha256(raw_end[0]).hexdigest() == observed['line_sha256'], 'Fin non liée à la ligne capturée.')
        end_ns = integer(observed['observed_monotonic_ns']); equal(end_ns, phase['end_observed_monotonic_ns'], 'Observation différente.')
        equal(stopped['helpers'], phase['helpers_stopped'], 'Identités arrêtées différentes.')
        require(len(stopped['helpers']) == len(phase['helpers']), 'Arrêts incomplets.')
        for old, current in zip(phase['helpers'], stopped['helpers']):
            require(current['pid'] == old['pid'] and current['previous_start_ticks'] == old['start_ticks']
                    and (current['reason'] == 'absent' or current['reason'] == 'pid_reused'
                         and type(current['current_start_ticks']) is int and current['current_start_ticks'] > 0
                         and current['current_start_ticks'] != old['start_ticks']), 'Identité encore présente ou réutilisation non distinguée.')
        first_empty, previous_read = None, None
        for sample_at, sample in anchored:
            require(sample['phase'] in ('before_start','running','drain'), 'Étiquette de phase inconnue.')
            if sample['phase'] == 'running':
                require(start[1] < sample_at < observed_at and sample['read_started_monotonic_ns'] >= start[3], 'Sondage périodique hors phase.')
            if previous_read is not None and sample['phase'] == 'running':
                require(sample['read_started_monotonic_ns'] - previous_read >= 250_000_000, 'Cadence périodique trop rapide.')
            previous_read = sample['read_finished_monotonic_ns']
            if sample['phase'] == 'drain':
                require(stopped_at < sample_at < collected_at and end_ns <= sample['read_started_monotonic_ns'], 'Vidage hors frontière.')
                empty = sample['statistics']['backlog_bytes'] == sample['statistics']['queued_packets'] == 0
                first_empty = (sample['read_finished_monotonic_ns'] if first_empty is None else first_empty) if empty else None
        last = phase_samples[-1]
        require(last['phase'] == 'drain' and first_empty is not None and last['read_finished_monotonic_ns'] - first_empty >= 500_000_000
                and proceed[3] <= end_ns <= last['read_finished_monotonic_ns'] <= advance[3] < end_ns + 3_000_000_000, 'Vidage ou advance hors délai.')
        delta = base.collect.cake.queue.statistics_delta(base.reading(phase_samples[0]), base.reading(last))
        require(delta['available'], 'Différence de phase indisponible.')
        equal(delta, phase['statistics_delta'], 'Différence de phase erronée.')
        equal(delta, collected['statistics_delta'], 'Différence journalisée erronée.')
    return {'schema_version':1, 'kind':'lab_cake_go_campaign_phase_review', 'phase_evidence_valid':True,
            'recorded_helper_pids':pids, 'phase_count':len(phases), 'measurements':assessment.assess(phases, crash=crash),
            'scope':'phases_only', 'native_certificate':False}


def replay(folder, report, tools, owned):
    """No signals/network/Git/build commands; caller must validate global context."""
    try:
        return _replay(folder, report, tools, owned)
    except Error:
        raise
    except Exception as error:
        raise Error('Relecture des phases refusée : '+str(error)) from error
