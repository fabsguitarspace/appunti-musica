"""Pipeline test with fake tools: no LilyPond, audio or PDF tools required.

Run with: python3 tests/test_build.py   (pytest also collects test_build)
Derived from tests/test_music_pipeline.py of appunti-pratica, extended for the
project/library split of ADR 0004.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LIBRARY = Path(__file__).resolve().parents[1]

FAKE_TOOL = '''#!/usr/bin/env python3
import os, sys
from pathlib import Path
n = Path(sys.argv[0]).name; a = sys.argv[1:]
with open(os.environ['CALLS_FILE'], 'a') as calls:
    calls.write(n + ' ' + repr(a) + '\\n')
if n == 'lilypond':
    p = Path(a[a.index('-o') + 1])
    p.with_suffix('.pdf').write_text('pdf'); p.with_suffix('.midi').write_text('midi')
elif n == 'pdf2svg':
    if Path(os.environ['FAIL_FILE']).exists(): sys.exit(1)
    Path(a[1]).write_text('svg')
elif n == 'fluidsynth':
    Path(a[a.index('-F') + 1]).write_text('wav')
elif n == 'lame':
    Path(a[1]).write_text('mp3')
'''


def test_build():
    with tempfile.TemporaryDirectory(prefix='music-check-') as tmp:
        r = Path(tmp)
        # Library copy: build script, one include, default SoundFont, one overlay.
        lib = r / 'tools/appunti-musica'
        (lib / 'appunti_musica').mkdir(parents=True)
        shutil.copy(LIBRARY / 'appunti_musica/build.py', lib / 'appunti_musica/build.py')
        (lib / 'lilypond/include').mkdir(parents=True)
        (lib / 'lilypond/include/common.ly').write_text('macro')
        (lib / 'sf').mkdir()
        (lib / 'sf/Jazzernaut.sf2').write_text('font')
        (lib / 'sf/Rhythm.sf2').write_text('library rhythm')
        # Project with spaces in its path; no include/ or sf/ of its own.
        project = r / 'my project'
        src = project / 'src/lilypond'
        src.mkdir(parents=True)
        (src / 'sample.ly').write_text('music')

        tools = r / 'bin'
        tools.mkdir()
        for n in ['lilypond', 'gs', 'pdf2svg', 'fluidsynth', 'lame']:
            p = tools / n
            p.write_text(FAKE_TOOL)
            p.chmod(0o755)
        (tools / 'pdfCropMargins.py').write_text(
            "import sys,shutil\na=sys.argv[1:];shutil.copyfile(a[-1],a[a.index('-o')+1])\n")
        calls = r / 'calls.txt'
        env = dict(os.environ, PYTHONPATH=str(tools), PATH=str(tools) + os.pathsep + os.environ['PATH'],
                   FAIL_FILE=str(r / 'fail'), CALLS_FILE=str(calls))
        out = project / 'src/docs/_static/music'
        cmd = [sys.executable, str(lib / 'appunti_musica/build.py'), '--project', str(project)]

        def run(ok=True, extra=()):
            x = subprocess.run(cmd + list(extra), env=env, capture_output=True, text=True, cwd=r)
            assert (x.returncode == 0) == ok, x.stdout + x.stderr
            return x.stdout

        # Default output directory inside the project; library include path passed to LilyPond.
        assert 'Compilo' in run()
        assert (out / 'sample.svg').is_file() and (out / 'sample.mp3').is_file()
        lily = [line for line in calls.read_text().splitlines() if line.startswith('lilypond ')]
        assert str(lib / 'lilypond') in lily[-1] and "'-I'" in lily[-1]
        assert str(lib / 'sf/Jazzernaut.sf2') in calls.read_text()
        assert 'Aggiornato' in run()

        # Invalidation: missing output, library include, project include, SoundFont, damaged output.
        (out / 'sample.midi').unlink(); assert 'Compilo' in run()
        (lib / 'lilypond/include/common.ly').write_text('changed'); assert 'Compilo' in run()
        assert 'Aggiornato' in run()
        (src / 'include').mkdir(); (src / 'include/local.ly').write_text('project macro')
        assert 'Compilo' in run()
        (src / 'include/local.ly').write_text('project macro 2'); assert 'Compilo' in run()
        (lib / 'sf/Jazzernaut.sf2').write_text('changed font'); assert 'Compilo' in run()
        (out / 'sample.svg').write_text('damaged'); assert 'Compilo' in run()

        # Failed conversion preserves previous outputs; recovery afterwards.
        before = (out / 'sample.pdf').read_bytes()
        (src / 'sample.ly').write_text('new'); (r / 'fail').touch(); run(False)
        assert (out / 'sample.pdf').read_bytes() == before
        (r / 'fail').unlink(); assert 'Compilo' in run(); assert 'Aggiornato' in run()

        # Declared overlay resolved from the library when the project has no sf/.
        (src / 'sample.ly').write_text('% soundfont-overlay: sf/Rhythm.sf2\nnew music')
        calls.write_text('')
        assert 'Compilo' in run()
        assert str(lib / 'sf/Rhythm.sf2') in calls.read_text()
        assert 'Aggiornato' in run()
        (lib / 'sf/Rhythm.sf2').write_text('changed library rhythm'); assert 'Compilo' in run()

        # A project file with the same path takes precedence over the library.
        (src / 'sf').mkdir(); (src / 'sf/Rhythm.sf2').write_text('project rhythm')
        calls.write_text('')
        assert 'Compilo' in run()
        assert str(src / 'sf/Rhythm.sf2') in calls.read_text()
        (src / 'sf/Rhythm.sf2').unlink(); (src / 'sf').rmdir()
        assert 'Compilo' in run()  # falls back to the library again

        # Command-line overlay; a missing overlay fails without touching outputs.
        overlay = r / 'rhythm with spaces.sf2'; overlay.write_text('cli rhythm')
        assert 'Compilo' in run(extra=['--soundfont-overlay', str(overlay)])
        manifest = (out / '.music-build/manifest.json').read_bytes(); pdf = (out / 'sample.pdf').read_bytes()
        overlay.unlink(); run(False, extra=['--soundfont-overlay', str(overlay)])
        assert (out / '.music-build/manifest.json').read_bytes() == manifest
        assert (out / 'sample.pdf').read_bytes() == pdf
        (src / 'sample.ly').write_text('% soundfont-overlay: sf/Missing.sf2\nmusic'); run(False)
        assert (out / 'sample.pdf').read_bytes() == pdf

        # Explicit output directory still supported.
        other = r / 'other out'
        (src / 'sample.ly').write_text('music')
        x = subprocess.run(cmd + ['--output-dir', str(other)], env=env, capture_output=True, text=True)
        assert x.returncode == 0, x.stderr
        assert (other / 'sample.svg').is_file()
        assert json.loads((other / '.music-build/manifest.json').read_text())['sample.ly']['outputs']


if __name__ == '__main__':
    test_build()
    print('PASS: project/library split, include path, default output, invalidation of library and '
          'project includes, SoundFont fallback and precedence, atomic recovery, overlays, spaces')
