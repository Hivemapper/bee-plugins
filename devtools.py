import argparse
import paramiko
import requests

from scp import SCPClient

HOST_IP = '192.168.0.10'
DEVICE_PLUGIN_ROUTE = f'http://{HOST_IP}:5000/api/1/plugin/'
PAUSE_UPDATES_ROUTE = DEVICE_PLUGIN_ROUTE + 'setPausePluginUpdates'

TEMPLATE_PLUGIN_PATH = '/data/plugins/template-plugin/template-plugin'

def toggle_dev_mode(pause_val):
  res = requests.post(PAUSE_UPDATES_ROUTE, json={"pausePluginUpdates": pause_val})
  if res.status != 200:
    raise Exception(res.json())

  return res.json()

def disable_dev_mode():
  toggle_dev_mode('false')

def enable_dev_mode():
  toggle_dev_mode('true')

def push_local_python_update(filepath):
  with paramiko.SSHClient() as ssh:
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST_IP, username='root')

    with SCPClient(ssh.get_transport()) as scp:
      scp.put(filepath, TEMPLATE_PLUGIN_PATH)

def restart_template_plugin_service():
  with paramiko.SSHClient() as ssh:
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST_IP, username='root')

    stdin, stdout, stderr = ssh.exec_command('systemctl restart template-plugin')  

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Local dev tooling for Bee Plugin development.")

  parser.add_argument('-dI', '--enable_devmode', help="Enable devmode.", action='store_true')
  parser.add_argument('-dO', '--disable_devmode', help="Disable devmode.", action='store_true')
  parser.add_argument('-i', '--input_file', help="Path to build.sh output .py file.", type=str)
  parser.add_argument('-R', '--restart_plugin', help="Restart plugin", action='store_true')

  args = parser.parse_args()

  if args.enable_devmode:
    enable_dev_mode()
    print('Dev Mode enabled')

  should_restart_service = args.restart_plugin

  if args.input_file:
    push_local_python_update(args.input_file)
    print(f'Updated plugin with {args.input_file}')
    should_restart_service = True

  if should_restart_service:
    print('Restarting plugin...')
    restart_template_plugin_service()

  if args.disable_devmode:
    disable_dev_mode()
    print('Dev Mode disabled')
