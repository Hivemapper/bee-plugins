# fmt: off
import argparse
import os
import paramiko

from util import do_json_post
from util.state_dump import collect_state_dump
from util.observation_dump import collect_observation_dump
from scp import SCPClient

HOST_IP = '192.168.197.55'
HOST = f'http://{HOST_IP}:5000'
API_ROUTE = f'{HOST}/api/1'
DEVICE_PLUGIN_ROUTE = f'{API_ROUTE}/plugin/'
PAUSE_UPDATES_ROUTE = DEVICE_PLUGIN_ROUTE + 'setPausePluginUpdates'

TEMPLATE_PLUGIN_PATH = '/data/plugins/template-plugin/template-plugin'

CACHE_DIR = '/data/cache';

def run_command_over_ssh(ssh, cmd):
  stdin, stdout, stderr = ssh.exec_command(cmd)

  stdout_output = stdout.read().decode().strip()
  stderr_output = stderr.read().decode().strip()

  if stdout_output:
    print(stdout_output)
  if stderr_output:
    raise Exception(stderr_output)  

def toggle_pause_plugin_updates(pause_val):
  data = {"pausePluginUpdates": pause_val}
  return do_json_post(PAUSE_UPDATES_ROUTE, data)

def resume_plugin_updates():
  toggle_pause_plugin_updates('false')

def pause_plugin_updates():
  toggle_pause_plugin_updates('true')

def push_local_python_update(filepath):
  with paramiko.SSHClient() as ssh:
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST_IP, username='root', password="", look_for_keys=False, allow_agent=False)

    with SCPClient(ssh.get_transport()) as scp:
      scp.put(filepath, TEMPLATE_PLUGIN_PATH)

    run_command_over_ssh(ssh, f'chmod 700 {TEMPLATE_PLUGIN_PATH}')

def restart_template_plugin_service():
  with paramiko.SSHClient() as ssh:
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST_IP, username='root', password="", look_for_keys=False, allow_agent=False)

    run_command_over_ssh(ssh, 'systemctl restart template-plugin')

def populate_fixture(fixture):
  with paramiko.SSHClient() as ssh:
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST_IP, username='root', password="", look_for_keys=False, allow_agent=False)

    with SCPClient(ssh.get_transport()) as scp:
      scp.put(f'fixtures/{fixture}', recursive=True, remote_path=CACHE_DIR)

def dump_cache():
  with paramiko.SSHClient() as ssh:
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST_IP, username='root', password="", look_for_keys=False, allow_agent=False)

    with SCPClient(ssh.get_transport()) as scp:
      scp.get(CACHE_DIR, recursive=True)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Local dev tooling for Bee Plugin development.")

  parser.add_argument('-dI', '--pause_plugin_updates', help="Pause plugin updates.", action='store_true')
  parser.add_argument('-dO', '--resume_plugin_updates', help="Resume plugin updates.", action='store_true')
  parser.add_argument('-i', '--input_file', help="Path to build.sh output .py file.", type=str)
  parser.add_argument('-R', '--restart_plugin', help="Restart plugin", action='store_true')
  parser.add_argument('-f', '--populate_fixture', help="Populate fixture data", type=str)
  parser.add_argument('-d', '--dump_cache', help='Copy cache contents to local machine', action='store_true')
  parser.add_argument('-sd', '--state_dump', help='Collect state dump from device', action='store_true')
  parser.add_argument('-co', '--cached-observations', help='Collect cached observation dump from device', action='store_true')

  args = parser.parse_args()

  if args.pause_plugin_updates:
    pause_plugin_updates()
    print('Plugin updates are paused.')

  should_restart_service = args.restart_plugin

  if args.input_file:
    push_local_python_update(args.input_file)
    print(f'Updated plugin with {args.input_file}')
    should_restart_service = True

  if should_restart_service:
    print('Restarting plugin...')
    restart_template_plugin_service()

  if args.resume_plugin_updates:
    resume_plugin_updates()
    print('Plugin updates are resumed.')

  if args.populate_fixture:
    populate_fixture(args.populate_fixture)

  if args.dump_cache:
    dump_cache()

  if args.state_dump:
    zip_filename = collect_state_dump(HOST_IP)
    if zip_filename:
      print(f"Created state dump {zip_filename}")

  if args.cached_observations:
    zip_filename = collect_observation_dump(HOST_IP)
    if zip_filename:
      print(f"Created cached observation dump {zip_filename}")
