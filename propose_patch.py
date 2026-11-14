"""One external model call per proposal, whose stdout is saved as candidate RTL."""
import difflib
import json
from pathlib import Path
import shlex


def propose(candidate, directory, command, run_command):
    root = Path(__file__).resolve().parent
    prompt = dict(instruction='Return only a complete replacement fifo.sv, without fences. '
                  'Only FIFO RTL may change. Preserve its module, interface, and '
                  'three-bit internal count used by the assertions.',
                  spec=(root / 'spec.md').read_text(), rtl=candidate.read_text(),
                  evidence=json.loads((directory / 'report.json').read_text()))
    payload = json.dumps(prompt, indent=2)
    (directory / 'prompt.json').write_text(payload)
    arguments = shlex.split(command)
    if not arguments:
        raise ValueError('repair command is empty')
    result = run_command(arguments, directory, 'model', 120, input_text=payload)
    (directory / 'response.txt').write_text(result.stdout)
    (directory / 'model.stderr').write_text(result.stderr)
    (directory / 'model.json').write_text(json.dumps(dict(returncode=result.returncode,
                                                        empty=not result.stdout.strip())) + '\n')
    if result.returncode or not result.stdout.strip():
        return None
    (directory / 'proposal.diff').write_text(''.join(difflib.unified_diff(
        candidate.read_text().splitlines(True), result.stdout.splitlines(True),
        fromfile='before/fifo.sv', tofile='after/fifo.sv')))
    output = directory / 'proposed.sv'
    output.write_text(result.stdout)
    return output
