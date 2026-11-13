#!/usr/bin/env python3
"""CT105-only pre-start gate; cannot block or modify other guests."""
import subprocess
import sys

if len(sys.argv) != 3 or sys.argv[1] != '105':
    raise SystemExit('This startup gate belongs exclusively to CT105')
if sys.argv[2] == 'pre-start':
    subprocess.run(['systemctl', 'start', 'infra-panel-network.service'], check=True)
    subprocess.run(['/usr/local/sbin/infra-panel-network', '--verify'], check=True)
