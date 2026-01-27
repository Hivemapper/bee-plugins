import re
import requests

from requests.exceptions import HTTPError

def do_json_get(url):
  res = requests.get(url)

  try:
    res.raise_for_status()
  except HTTPError as http_err:
    try:
      print(res.json())
    except Exception:
      pass

    raise

  return res.json()

def do_json_post(url, data=None):
  res = requests.post(url, json=data)

  try:
    res.raise_for_status()
  except HTTPError as http_err:
    try:
      print(res.json())
    except Exception:
      pass

    raise

  return res.json()
