import os
import json
import time
import zipfile
import requests
import paramiko
from scp import SCPClient
import shutil
from datetime import datetime
from tqdm import tqdm

def collect_state_dump(host_ip):
    timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    dump_dir = f'state_dump_{timestamp}'
    api_dir = os.path.join(dump_dir, 'api')
    os.makedirs(api_dir, exist_ok=True)
    
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
                    filename = endpoint.split('/')[-1] + '.json'
                    url = f'http://{host_ip}:5000{endpoint}'
                    try:
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            with open(os.path.join(api_dir, filename), 'w') as f:
                                json.dump(response.json(), f, indent=2)
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
                        
                        dest_path = os.path.join(dump_dir, os.path.basename(remote_file))
                        if os.path.exists(dest_path):
                            dest_path = os.path.join(dump_dir, f"{os.path.basename(os.path.dirname(remote_file))}_{os.path.basename(remote_file)}")
                        
                        try:
                            scp.get(remote_file, local_path=dest_path)
                            results["files"][remote_file] = "success"
                        except Exception as e:
                            results["files"][remote_file] = f"failed (error: {str(e)})"
                        pbar.update(1)

                # Save results.json
                pbar.set_postfix_str("saving summary")
                with open(os.path.join(dump_dir, 'results.json'), 'w') as f:
                    json.dump(results, f, indent=2)
                pbar.update(1)

                # PHASE: archive
                pbar.set_postfix_str("archive")
                zip_filename = f'state-dump-{timestamp}.zip'
                archive_name = f'state-dump-{timestamp}'
                try:
                    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(dump_dir):
                            for file in files:
                                # Full path to the file
                                file_path = os.path.join(root, file)
                                # Relative path within dump_dir (keeps subdirectories like api/)
                                rel_path = os.path.relpath(file_path, dump_dir)
                                # Write file into the zip with a prefix directory
                                zipf.write(file_path, arcname=os.path.join(archive_name, rel_path))
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
