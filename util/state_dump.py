import json
import re
import zipfile
import requests
import paramiko
import shutil
from pathlib import Path
from scp import SCPClient
from datetime import datetime
from tqdm import tqdm


# Known failure patterns from CAP-96 investigation
LOG_PATTERNS = {
    'gps_not_locked': {
        'pattern': re.compile(r'GPS is not locked'),
        'severity': 'high',
        'description': 'GPS not locked — may prevent session readiness and FrameKM packing',
    },
    'session_not_ready': {
        'pattern': re.compile(r'Waiting for session to be ready'),
        'severity': 'high',
        'description': 'Session not ready — FrameKM packing blocked',
    },
    'nothing_to_pack': {
        'pattern': re.compile(r'Nothing to pack, waiting for finished FrameKMs'),
        'severity': 'medium',
        'description': 'No FrameKMs to pack — no data being generated for upload',
    },
    'no_ip_lte': {
        'pattern': re.compile(r'No IP address for LTE interface'),
        'severity': 'medium',
        'description': 'No LTE connectivity — uploads will fail',
    },
    'internet_not_healthy': {
        'pattern': re.compile(r'Internet is not healthy'),
        'severity': 'medium',
        'description': 'Internet connectivity unhealthy',
    },
    'redis_timeout': {
        'pattern': re.compile(r'redis.*(?:timeout|i/o timeout|connection refused)', re.IGNORECASE),
        'severity': 'medium',
        'description': 'Redis connectivity issue — may indicate boot race condition',
    },
    'fsync_error': {
        'pattern': re.compile(r'fsync.*error|repeated fsync errors', re.IGNORECASE),
        'severity': 'high',
        'description': 'Filesystem sync errors — possible storage media degradation',
    },
    'classifier_timeout': {
        'pattern': re.compile(r'No input received from any classifier'),
        'severity': 'medium',
        'description': 'Classifier pipeline timeout — DepthAI classification routing issue',
    },
}


def _analyze_log_file(log_path):
    """Scan a log file for known failure patterns. Returns list of findings."""
    findings = []
    try:
        with open(log_path, 'r', errors='replace') as f:
            lines = f.readlines()
    except Exception:
        return findings

    counts = {name: 0 for name in LOG_PATTERNS}
    first_occurrence = {}

    for i, line in enumerate(lines):
        for name, info in LOG_PATTERNS.items():
            if info['pattern'].search(line):
                counts[name] += 1
                if name not in first_occurrence:
                    first_occurrence[name] = i + 1

    for name, count in counts.items():
        if count > 0:
            info = LOG_PATTERNS[name]
            findings.append({
                'pattern': name,
                'count': count,
                'severity': info['severity'],
                'description': info['description'],
                'first_line': first_occurrence.get(name),
            })

    return findings


def _analyze_clock_sync(api_results):
    """Analyze collected API data for clock sync issues (CAP-96 root cause)."""
    diagnostics = {
        'clock_synced': None,
        'drift_secs': None,
        'system_time': None,
        'gnss_time': None,
        'gps_locked': None,
        'internet_healthy': None,
        'warnings': [],
    }

    # Check /api/1/time/latest for clock drift
    time_data = api_results.get('/api/1/time/latest')
    if isinstance(time_data, dict):
        syncd = time_data.get('syncd', {})
        sys_time_str = syncd.get('system_time', '')
        utc_time_str = syncd.get('utc_time', '')
        diagnostics['system_time'] = sys_time_str
        diagnostics['gnss_time'] = utc_time_str

        if sys_time_str and utc_time_str:
            try:
                fmt = '%Y-%m-%d %H:%M:%S'
                sys_dt = datetime.strptime(sys_time_str[:19], fmt)
                utc_dt = datetime.strptime(utc_time_str[:19], fmt)
                drift = abs((sys_dt - utc_dt).total_seconds())
                diagnostics['drift_secs'] = drift
                diagnostics['clock_synced'] = drift <= 60
                if drift > 60:
                    diagnostics['warnings'].append(
                        f'CRITICAL: System clock drift of {drift:.0f}s detected. '
                        f'System={sys_time_str}, GNSS={utc_time_str}. '
                        'This is the CAP-96 root cause — GPS will not be considered '
                        'locked, preventing session readiness and FrameKM generation.'
                    )
            except (ValueError, TypeError):
                pass

    # Check /api/1/info for GPS lock and internet
    info_data = api_results.get('/api/1/info')
    if isinstance(info_data, dict):
        diagnostics['gps_locked'] = info_data.get('hasGnssLock')
        diagnostics['internet_healthy'] = info_data.get('internetIsHealthy')

        if info_data.get('hasGnssLock') is False:
            diagnostics['warnings'].append(
                'GPS is not locked. If clock drift is present, this is expected '
                '(CAP-96). Check /api/1/time/latest for clock sync status.'
            )

        if info_data.get('internetIsHealthy') is False:
            diagnostics['warnings'].append(
                'Internet connectivity is unhealthy — uploads will fail.'
            )

    # Check GNSS data for valid fix despite no lock
    gnss_data = api_results.get('/api/1/gnssConcise/latestValid')
    if isinstance(gnss_data, dict) and gnss_data.get('gnss_fix_ok') == 1:
        if diagnostics['gps_locked'] is False:
            diagnostics['warnings'].append(
                f'GNSS module has valid fix (fix={gnss_data.get("fix")}, '
                f'gnss_fix_ok=1, sats={gnss_data.get("satellites_used")}) '
                'but GPS is not reported as locked — clock drift is likely '
                'preventing lock acceptance.'
            )

    return diagnostics


def collect_state_dump(host_ip):
    timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    dump_dir = Path(f'state_dump_{timestamp}')
    api_dir = dump_dir / 'api'
    api_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "api_endpoints": {},
        "files": {},
        "diagnostics": {},
        "log_analysis": {},
        "archive": "pending"
    }

    # 1. API Endpoints (including GNSS/GPS and time sync endpoints for CAP-96 diagnosis)
    endpoints = [
        '/api/1/info',
        '/api/1/ping',
        '/api/1/time/latest',
        '/api/1/gps/sample',
        '/api/1/gnssConcise/latestValid',
        '/api/1/framekm/unprocessed',
        '/api/1/recordings/cameraReady',
        '/api/1/locktime',
        '/api/1/lte-debug-info',
        '/api/1/lte-debug-check-auth',
        '/api/1/plugins',
        '/api/1/config',
    ]

    # Files via SSH/SCP (to get counts first)
    remote_paths = [
        ('/data/', '*.log*'),
        ('/data/recording/', '*.log*'),
        ('/data/recording/', '*.db'),
        ('/data/recording/', '*.db-shm'),
        ('/data/recording/', '*.db-wal'),
    ]

    all_remote_files = []
    api_responses = {}

    try:
        with paramiko.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host_ip, username='root', password="", look_for_keys=False, allow_agent=False)
            results["ssh_connection"] = "success"

            # Find all files first to set progress bar total
            for remote_dir, pattern in remote_paths:
                cmd = f'ls -1 {remote_dir}{pattern} 2>/dev/null'
                stdin, stdout, stderr = ssh.exec_command(cmd)
                files = stdout.read().decode().splitlines()
                all_remote_files.extend(files)

            # +1 for results.json, +1 for archive, +1 for diagnostics
            total_steps = len(endpoints) + len(all_remote_files) + 3

            with tqdm(total=total_steps, unit="item", desc="State Dump") as pbar:
                # PHASE: api fetch
                pbar.set_postfix_str("api fetch")
                for endpoint in endpoints:
                    filename = endpoint.replace('/api/1/', '').replace('/', '_') + '.json'
                    url = f'http://{host_ip}:5000{endpoint}'
                    try:
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            json_path = api_dir / filename
                            json_path.write_text(json.dumps(data, indent=2))
                            results["api_endpoints"][endpoint] = "success"
                            api_responses[endpoint] = data
                        else:
                            results["api_endpoints"][endpoint] = f"failed (status code: {response.status_code})"
                    except Exception as e:
                        results["api_endpoints"][endpoint] = f"failed (error: {str(e)})"
                    pbar.update(1)

                # PHASE: file transfer
                with SCPClient(ssh.get_transport()) as scp:
                    for remote_file in all_remote_files:
                        pbar.set_postfix_str("file transfer")

                        rel_remote_path = Path(remote_file).relative_to('/')
                        dest_path = dump_dir / rel_remote_path
                        dest_path.parent.mkdir(parents=True, exist_ok=True)

                        try:
                            scp.get(remote_file, local_path=str(dest_path))
                            results["files"][remote_file] = "success"
                        except Exception as e:
                            results["files"][remote_file] = f"failed (error: {str(e)})"
                        pbar.update(1)

                # PHASE: diagnostics
                pbar.set_postfix_str("diagnostics")

                # Clock sync and GPS analysis
                results["diagnostics"] = _analyze_clock_sync(api_responses)

                # Log file analysis for known failure patterns
                log_dir = dump_dir / 'data'
                if log_dir.exists():
                    for log_file in log_dir.rglob('*.log*'):
                        findings = _analyze_log_file(log_file)
                        if findings:
                            rel = str(log_file.relative_to(dump_dir))
                            results["log_analysis"][rel] = findings
                pbar.update(1)

                # Save results.json
                pbar.set_postfix_str("saving summary")
                results_path = dump_dir / 'results.json'
                results_path.write_text(json.dumps(results, indent=2))
                pbar.update(1)

                # Print diagnostic warnings
                if results["diagnostics"].get("warnings"):
                    print("\n--- Device Diagnostics ---")
                    for w in results["diagnostics"]["warnings"]:
                        print(f"  ! {w}")

                if results["log_analysis"]:
                    print("\n--- Log Analysis ---")
                    for log_file, findings in results["log_analysis"].items():
                        for f in findings:
                            if f['count'] > 0:
                                print(f"  [{f['severity'].upper()}] {log_file}: "
                                      f"{f['description']} ({f['count']}x)")

                # PHASE: archive
                pbar.set_postfix_str("archive")
                zip_filename = f'state-dump-{timestamp}.zip'
                archive_name = Path(f'state-dump-{timestamp}')
                try:
                    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for file_path in dump_dir.rglob('*'):
                            if file_path.is_file():
                                rel_path = file_path.relative_to(dump_dir)
                                zipf.write(file_path, arcname=str(archive_name / rel_path))

                    results["archive"] = "success"
                    pbar.update(1)
                    pbar.set_postfix_str("complete")

                    # Cleanup the temporary directory
                    shutil.rmtree(dump_dir)
                except Exception as e:
                    results["archive"] = f"failed (error: {str(e)})"
                    print(f"Failed to create archive: {e}")

    except Exception as e:
        results["ssh_connection"] = f"failed (error: {str(e)})"
        print(f"SSH Error: {e}")
        return None

    return zip_filename
