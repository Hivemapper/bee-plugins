import zipfile
import paramiko
import shutil
from pathlib import Path
from scp import SCPClient
from datetime import datetime
from tqdm import tqdm

def collect_observation_dump(host_ip):
    timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    dump_dir = Path(f'observation_dump_{timestamp}')
    dump_dir.mkdir(parents=True, exist_ok=True)
    
    remote_dir = '/data/recording/cached_observations/'
    
    try:
        with paramiko.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host_ip, username='root', password="", look_for_keys=False, allow_agent=False, timeout=10)
            
            # Find all files to set progress bar total
            cmd = f'find {remote_dir} -type f 2>/dev/null'
            stdin, stdout, stderr = ssh.exec_command(cmd)
            all_remote_files = stdout.read().decode().splitlines()

            if not all_remote_files:
                print(f"No files found in {remote_dir}")
                shutil.rmtree(dump_dir)
                return None

            total_steps = len(all_remote_files) + 1 # +1 for archive
            
            with tqdm(total=total_steps, unit="item", desc="Observation Dump") as pbar:
                # PHASE: file transfer
                with SCPClient(ssh.get_transport()) as scp:
                    pbar.set_postfix_str("downloading")
                    # Assuming flat or simple structure, scp.get into dump_dir
                    # We still do it one by one to keep the progress bar moving
                    for remote_file in all_remote_files:
                        dest_path = dump_dir / Path(remote_file).name
                        scp.get(remote_file, local_path=str(dest_path))
                        pbar.update(1)

                # PHASE: archive
                pbar.set_postfix_str("archiving")
                zip_filename = f'cached-observations-{timestamp}.zip'
                archive_name = Path(f'cached-observations-{timestamp}')
                try:
                    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for file_path in dump_dir.glob('*'):
                            if file_path.is_file():
                                # Write file into the zip with a prefix directory
                                zipf.write(file_path, arcname=str(archive_name / file_path.name))
                    
                    pbar.update(1)
                    pbar.set_postfix_str("complete")
                    
                    # Cleanup the temporary directory
                    shutil.rmtree(dump_dir)
                except Exception as e:
                    print(f"Failed to create archive: {e}")
                    return None

    except Exception as e:
        print(f"Error during observation dump: {e}")
        if dump_dir.exists():
            shutil.rmtree(dump_dir)
        return None

    return zip_filename
