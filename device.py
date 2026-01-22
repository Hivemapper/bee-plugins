import argparse
import paramiko
import requests

from requests.exceptions import HTTPError
from scp import SCPClient

HOST_IP = '192.168.0.10'
HOST = f'http://{HOST_IP}:5000'
API_ROUTE = f'{HOST}/api/1'
WIFI_ROUTE = f'{HOST}/wifiClient'
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
  res = requests.post(CONNECTIVITY_ROUTE, json={'mode': mode})

  try:
    res.raise_for_status()
  except HTTPError as http_err:
    try:
      print(res.json())
    except Exception:
      pass

    raise

  return res.json()

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
  res = requests.post(WIFI_ROUTE + '/settings', json=config)

  try:
    res.raise_for_status()
  except HTTPError as http_err:
    try:
      print(res.json())
    except Exception:
      pass

    raise

  return res.json()

def scan_wifi_networks():
  res = requests.get(WIFI_ROUTE + '/scan')

  try:
    res.raise_for_status()
  except HTTPError as http_err:
    try:
      print(res.json())
    except Exception:
      pass

    raise

  return res.json()

def wifi_settings():
  res = requests.get(WIFI_ROUTE + '/settings')

  try:
    res.raise_for_status()
  except HTTPError as http_err:
    try:
      print(res.json())
    except Exception:
      pass

    raise

  return res.json()  

def wifi_status():
  res = requests.get(WIFI_ROUTE + '/status')

  try:
    res.raise_for_status()
  except HTTPError as http_err:
    try:
      print(res.json())
    except Exception:
      pass

    raise

  return res.json()

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Local dev tooling for Bee Plugin development.")

  parser.add_argument('-L', '--lte', help="Use LTE for connectivity", action='store_true')
  parser.add_argument('-W', '--wifi_info', help="Show WiFi status", action='store_true')
  parser.add_argument('-Ws', '--wifi_scan', help="Show visible WiFi networks", action='store_true')
  parser.add_argument('-Wi', '--wifi_ssid', help="Use WiFi SSID for connectivity", type=str)
  parser.add_argument('-P', '--password', help="Password", type=str, default="")

  args = parser.parse_args()

  if args.wifi_info:
    print(wifi_status())
    print(wifi_settings())

  if args.wifi_scan:
    print(scan_wifi_networks())

  if args.lte:
    switch_to_lte_client_mode()
  elif args.wifi_ssid:
    switch_to_lte_client_mode()
    connect_to_wifi_network(args.wifi_ssid, args.password)    
