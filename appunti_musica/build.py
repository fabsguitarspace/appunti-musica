#!/usr/bin/env python3
"""Build musical assets of a project in staging; commit fingerprints only after success.

Shared by appunti-teoria, appunti-pratica and appunti-repertorio (ADR 0004).
The project supplies src/lilypond/*.ly; this library supplies the LilyPond
include path (lilypond/include), the default SoundFont and declared overlays
(sf/). A project file with the same relative path takes precedence.
"""
import argparse
import fcntl
import hashlib
import importlib.metadata
import sys
import json
import os
import re
import shlex
from pathlib import Path
import shutil
import subprocess
import tempfile

LIBRARY = Path(__file__).resolve().parents[1]
LIBRARY_LILYPOND = LIBRARY / 'lilypond'
LIBRARY_SF = LIBRARY / 'sf'
TOOLS = ('lilypond', 'gs', 'pdf2svg', 'fluidsynth', 'lame')
RECIPE = 3


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def run(args, log, cwd):
    subprocess.run([str(x) for x in args], cwd=cwd, stdout=log,
                   stderr=subprocess.STDOUT, check=True)


def save_manifest(path, data):
    pending = path.with_suffix('.pending')
    pending.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    os.replace(pending, path)


def locate(base, name):
    """Resolve a SoundFont path: project file first, then the library's sf/."""
    local = base / name
    if local.is_file():
        return local.resolve()
    if name.startswith('sf/') and (LIBRARY_SF / name[3:]).is_file():
        return (LIBRARY_SF / name[3:]).resolve()
    return local.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd(),
                        help='Project root containing src/lilypond (default: current directory)')
    parser.add_argument('--output-dir', type=Path,
                        help='Default: PROJECT/src/docs/_static/music')
    parser.add_argument('--source', action='append', help='Source basename, repeatable (default: all)')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--mp3-options', default='',
                        help='Extra lame options, e.g. "-m m -b 64" (default: lame defaults, 128 kbps stereo)')
    parser.add_argument('--soundfont-overlay', action='append', type=Path, default=[],
                        help='Additional SoundFont, loaded after the default (repeatable)')
    args = parser.parse_args()
    mp3_options = shlex.split(args.mp3_options)
    root = args.project.resolve()
    sources_dir = root / 'src/lilypond'
    if args.output_dir is None:
        args.output_dir = root / 'src/docs/_static/music'
    sources = sorted(sources_dir.glob('*.ly'))
    if args.source:
        requested = set(args.source)
        unknown = requested - {p.stem for p in sources}
        if unknown:
            parser.error('Unknown sources: ' + ', '.join(sorted(unknown)))
        sources = [p for p in sources if p.stem in requested]
    if not sources:
        parser.error('No LilyPond sources found')
    tools = {name: shutil.which(name) for name in TOOLS}
    missing = [name for name, path in tools.items() if path is None]
    if missing:
        parser.error('Missing required tools: ' + ', '.join(missing))
    try:
        crop_version = importlib.metadata.version('pdfCropMargins')
        mupdf_version = importlib.metadata.version('PyMuPDF')
    except importlib.metadata.PackageNotFoundError:
        parser.error('Missing cropping dependencies: install requirements-music.txt with this Python')
    soundfont = locate(sources_dir, 'sf/Jazzernaut.sf2')
    if not soundfont.is_file():
        parser.error('Missing soundfont: ' + str(soundfont))
    # Hash executables rather than relying on inconsistent --version options.
    tool_hashes = {name: digest(Path(path)) for name, path in tools.items()}
    # Project includes shadow library includes with the same path (LilyPond
    # searches the source directory before -I); both enter the fingerprint.
    includes = {'library:' + str(p.relative_to(LIBRARY_LILYPOND)): digest(p)
                for p in sorted(LIBRARY_LILYPOND.rglob('*'))
                if p.is_file() and p.suffix in ('.ly', '.ily')}
    includes.update({'project:' + str(p.relative_to(sources_dir)): digest(p)
                     for p in sorted(sources_dir.rglob('*'))
                     if p.is_file() and p.suffix in ('.ly', '.ily') and p.parent != sources_dir})
    source_fonts = {}
    for src in sources:
        declared = [locate(src.parent, name.strip()) for name in re.findall(
            r'^% soundfont-overlay:([^\n]+)$', src.read_text(), re.MULTILINE)]
        soundfonts = list(dict.fromkeys(
            [soundfont] + [p.resolve() for p in declared + args.soundfont_overlay]))
        for overlay in soundfonts[1:]:
            if not overlay.is_file():
                parser.error('Missing SoundFont overlay: ' + str(overlay))
        source_fonts[src] = soundfonts
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    state = out / '.music-build'
    state.mkdir(exist_ok=True)
    with (state / 'lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('Another build is using this output directory')
        manifest_path = state / 'manifest.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        for src in sources:
            soundfonts = source_fonts[src]
            soundfont_hash = (digest(soundfont) if len(soundfonts) == 1 else
                              [digest(path) for path in soundfonts])
            key = signature({'recipe': RECIPE, 'source': digest(src), 'includes': includes,
                             'tools': tool_hashes, 'crop': [crop_version, mupdf_version],
                             'builder': digest(Path(__file__)), 'soundfont': soundfont_hash,
                             **({'mp3': mp3_options} if mp3_options else {})})
            previous = manifest.get(src.name, {})
            products = previous.get('outputs', {})
            valid = (previous.get('signature') == key and products and
                     all((out / name).is_file() and digest(out / name) == value
                         for name, value in products.items()))
            if valid and not args.force:
                print('Aggiornato:', src.name, flush=True)
                continue
            print('Compilo:', src.name, flush=True)
            log_path = state / (src.stem + '.log')
            # Staging shares the destination filesystem, allowing atomic file replacement.
            with tempfile.TemporaryDirectory(prefix='stage-', dir=state) as folder:
                stage = Path(folder)
                base = stage / src.stem
                try:
                    with log_path.open('w') as log:
                        run([tools['lilypond'], '-I', LIBRARY_LILYPOND, '-o', base, src], log, root)
                        pdf = base.with_suffix('.pdf')
                        if not pdf.is_file() or not pdf.stat().st_size:
                            raise RuntimeError('Expected PDF missing: ' + str(pdf))
                        # Preserve the existing single-PDF/SVG contract; reject silent truncation.
                        pdfs = list(stage.glob('*.pdf'))
                        midis = list(stage.glob('*.midi'))
                        if len(pdfs) != 1 or len(midis) > 1 or any(p.stem != src.stem for p in midis):
                            raise RuntimeError('Multiple/nonnormal output names need an explicit output contract')
                        cropped = stage / 'cropped.pdf'
                        run([sys.executable, '-m', 'pdfCropMargins', '-p', '0', '-a', '-10',
                             '-c', 'gb', '-o', cropped, pdf], log, root)
                        os.replace(cropped, pdf)
                        run([tools['pdf2svg'], pdf, base.with_suffix('.svg')], log, root)
                        names = [src.stem + '.pdf', src.stem + '.svg']
                        if midis:
                            wav = base.with_suffix('.wav')
                            run([tools['fluidsynth'], '-F', wav, '-ni', *soundfonts, midis[0]], log, root)
                            run([tools['lame'], *mp3_options, wav, base.with_suffix('.mp3')], log, root)
                            names += [src.stem + '.midi', src.stem + '.mp3']
                    for name in names:
                        if not (stage / name).is_file() or not (stage / name).stat().st_size:
                            raise RuntimeError('Empty or missing output: ' + name)
                    # Invalidate before promotion so interruption never leaves a success marker.
                    manifest.pop(src.name, None)
                    save_manifest(manifest_path, manifest)
                    for name in names:
                        os.replace(stage / name, out / name)
                    manifest[src.name] = {'signature': key,
                                          'outputs': {name: digest(out / name) for name in names}}
                    save_manifest(manifest_path, manifest)
                    leftovers = set(products) - set(names)
                    if leftovers:
                        print('Risorse precedenti conservate, da verificare:', ', '.join(sorted(leftovers)))
                except (subprocess.CalledProcessError, RuntimeError) as error:
                    raise RuntimeError(f'{src.name}: {error}. Log: {log_path}') from error
        removed = set(manifest) - {p.name for p in sources_dir.glob('*.ly')}
        if removed:
            print('Sorgenti rimossi; output conservati da verificare:', ', '.join(sorted(removed)))


if __name__ == '__main__':
    main()
