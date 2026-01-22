import argparse
import paramiko

from scp import SCPClient
from pprint import pp
from util import do_json_get, do_json_post

HOST_IP = '192.168.0.10'
HOST = f'http://{HOST_IP}:5000'
API_ROUTE = f'{HOST}/api/1'
WIFI_ROUTE = f'{API_ROUTE}/wifiClient'
CONNECTIVITY_ROUTE = f'{API_ROUTE}/config/uploadMode'

TEMPLATE_PLUGIN_PATH = '/data/plugins/template-plugin/template-plugin'

def run_command_over_ssh(ssh, cmd):
  stdin, stdout, stderr = ssh.exec_command(cmd)

  stdout_output = stdout.read().decode().strip()
  stderr_output = stderr.read().decode().strip()

  if stdout_output:
    print(stdout_output)
  if stderr_output:
    raise Exception(stderr_output)

def toggle_client_connectivity_mode(mode):
  return do_json_post(CONNECTIVITY_ROUTE, {'mode': mode})

def switch_to_lte_client_mode():
  toggle_client_connectivity_mode('lte')

def switch_to_wifi_client_mode():
  toggle_client_connectivity_mode('wifi')

def connect_to_wifi_network(ssid, password, security='WPA2', freq=2417):
  config = {
    'ssid': ssid,
    'password': password,
    'enabled': 'true',
    'security': security,
    'freq': freq,
  }

  url = WIFI_ROUTE + '/settings'
  return do_json_post(url, config)

def scan_wifi_networks():
  url = WIFI_ROUTE + '/scan'
  return do_json_get(url)

def wifi_settings():
  url = WIFI_ROUTE + '/settings'
  return do_json_get(url)

def wifi_status():
  url = WIFI_ROUTE + '/status'
  return do_json_get(url)

def info():
  url = f'{API_ROUTE}/info'
  res = do_json_get(url)
  return res

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Local dev tooling for Bee Plugin development.")

  parser.add_argument('-I', '--info', help="Device info", action='store_true')
  parser.add_argument('-L', '--lte', help="Use LTE for connectivity", action='store_true')
  parser.add_argument('-W', '--wifi_info', help="Show WiFi status", action='store_true')
  parser.add_argument('-Ws', '--wifi_scan', help="Show visible WiFi networks", action='store_true')
  parser.add_argument('-Wi', '--wifi_ssid', help="Use WiFi SSID for connectivity", type=str)
  parser.add_argument('-P', '--password', help="Password", type=str, default="")

  args = parser.parse_args()

  if args.info:
    pp(info())

  if args.wifi_info:
    pp(wifi_status())

  if args.wifi_scan:
    pp(scan_wifi_networks())

  if args.lte:
    switch_to_lte_client_mode()
  elif args.wifi_ssid:
    switch_to_lte_client_mode()
    connect_to_wifi_network(args.wifi_ssid, args.password)    
