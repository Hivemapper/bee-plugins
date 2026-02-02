import json
import zipfile
import requests
import paramiko
import shutil
from pathlib import Path
from scp import SCPClient
from datetime import datetime
from tqdm import tqdm

def collect_state_dump(host_ip):
    timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    dump_dir = Path(f'state_dump_{timestamp}')
    api_dir = dump_dir / 'api'
    api_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        "api_endpoints": {},
        "files": {},
        "archive": "pending"
    }
    
    # 1. API Endpoints
    endpoints = [
        '/api/1/info',
        '/api/1/lte-debug-info',
        '/api/1/lte-debug-check-auth',
        '/api/1/plugins',
        '/api/1/config'
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

            total_steps = len(endpoints) + len(all_remote_files) + 2 # +1 for results.json, +1 for archive
            
            with tqdm(total=total_steps, unit="item", desc="State Dump") as pbar:
                # PHASE: api fetch
                pbar.set_postfix_str("api fetch")
                for endpoint in endpoints:
                    filename = f"{endpoint.split('/')[-1]}.json"
                    url = f'http://{host_ip}:5000{endpoint}'
                    try:
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            json_path = api_dir / filename
                            json_path.write_text(json.dumps(response.json(), indent=2))
                            results["api_endpoints"][endpoint] = "success"
                        else:
                            results["api_endpoints"][endpoint] = f"failed (status code: {response.status_code})"
                    except Exception as e:
                        results["api_endpoints"][endpoint] = f"failed (error: {str(e)})"
                    pbar.update(1)

                # PHASE: file transfer
                with SCPClient(ssh.get_transport()) as scp:
                    for remote_file in all_remote_files:
                        pbar.set_postfix_str("file transfer")
                        
                        remote_path_obj = Path(remote_file)
                        dest_path = dump_dir / remote_path_obj.name
                        
                        if dest_path.exists():
                            # If file exists, prefix with parent directory name to avoid collision
                            dest_path = dump_dir / f"{remote_path_obj.parent.name}_{remote_path_obj.name}"
                        
                        try:
                            scp.get(remote_file, local_path=str(dest_path))
                            results["files"][remote_file] = "success"
                        except Exception as e:
                            results["files"][remote_file] = f"failed (error: {str(e)})"
                        pbar.update(1)

                # Save results.json
                pbar.set_postfix_str("saving summary")
                results_path = dump_dir / 'results.json'
                results_path.write_text(json.dumps(results, indent=2))
                pbar.update(1)

                # PHASE: archive
                pbar.set_postfix_str("archive")
                zip_filename = f'state-dump-{timestamp}.zip'
                archive_name = Path(f'state-dump-{timestamp}')
                try:
                    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for file_path in dump_dir.rglob('*'):
                            if file_path.is_file():
                                rel_path = file_path.relative_to(dump_dir)
                                # Write file into the zip with a prefix directory
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
