# appunti-musica

Pipeline musicale comune ai tre progetti di appunti per chitarra jazz:

- [appunti-teoria](https://github.com/fabsguitarspace/appunti-teoria)
- [appunti-pratica](https://github.com/fabsguitarspace/appunti-pratica)
- [appunti-repertorio](https://github.com/fabsguitarspace/appunti-repertorio)

La decisione e il piano di migrazione sono nell'ADR 0004 «Libreria musicale comune», presente in ciascun progetto in `Docs/adr/`, e nell'analisi 002 di appunti-repertorio.

## Contenuto

| Percorso | Contenuto |
|---|---|
| `appunti_musica/build.py` | LilyPond → PDF → ritaglio → SVG; MIDI → WAV → MP3, con cache a impronte e sostituzione atomica degli output |
| `appunti_musica/rhythm_soundfont.py` | genera in modo deterministico `sf/PracticeRhythm.sf2` (basso e batteria originali, nessun campione di terzi) |
| `lilypond/include/` | macro `my-chart.ly` e `my-scales.ly` |
| `sf/Jazzernaut.sf2` | soundfont predefinito |
| `sf/PracticeRhythm.sf2` | soundfont aggiuntivo per basso e batteria |
| `tests/test_build.py` | test della pipeline con strumenti simulati |

Origine: `build.py`, le macro, i soundfont e il generatore vengono da appunti-pratica. La sua versione dello script contiene già tutte le funzioni di quella di appunti-teoria. Ad appunti-teoria va comunque `my-scales.ly` di Pratica, perché nessuno dei suoi spartiti la usa.

I moduli Python condivisi dai generatori (voicing, basi) verranno aggiunti quando serviranno ad almeno due progetti. Il primo caso previsto è il generatore degli standard di appunti-repertorio.

## Uso in un progetto

La libreria si collega come sottomodulo git in `tools/appunti-musica`:

```sh
git submodule add https://github.com/fabsguitarspace/appunti-musica.git tools/appunti-musica
```

Per clonare un progetto insieme alla libreria:

```sh
git clone --recurse-submodules <url-del-progetto>
```

oppure, dentro un clone già esistente:

```sh
git submodule update --init
```

`build-lilypond.sh` del progetto richiama la build della libreria:

```sh
"$PYTHON" "$PROJECT_DIR/tools/appunti-musica/appunti_musica/build.py" --project "$PROJECT_DIR" "$@"
```

Opzioni: `--source NOME` (ripetibile), `--force`, `--output-dir`, `--soundfont-overlay FILE`. Senza `--output-dir`, gli output vanno in `PROGETTO/src/docs/_static/music`.

### Come vengono risolti i percorsi

- I sorgenti si trovano in `PROGETTO/src/lilypond/*.ly`.
- `\include "include/my-scales.ly"`: LilyPond cerca prima nella cartella del sorgente, poi nella cartella `lilypond/` della libreria, passata con `-I`. Una macro del progetto con lo stesso percorso ha quindi la precedenza.
- `sf/Jazzernaut.sf2` e `% soundfont-overlay: sf/NOME.sf2`: si usa prima `PROGETTO/src/lilypond/sf/NOME.sf2`, se esiste, poi `sf/NOME.sf2` della libreria.
- Le macro della libreria e del progetto e tutti i soundfont usati entrano nell'impronta di ogni sorgente: se cambiano, il sorgente viene ricompilato.

## Requisiti

- Strumenti: `lilypond` (verificato con 2.26.0), `gs`, `pdf2svg`, `fluidsynth`, `lame`.
- Python 3.12 o successivo, con `pip install -r requirements-music.txt`.

## Test

```sh
python tests/test_build.py
```

Va eseguito con un Python in cui sia installato `requirements-music.txt`. Gli strumenti esterni sono simulati.

## Aggiornare la libreria in un progetto

1. Applicare la modifica in questo repository, con un test se tocca la pipeline, e fare commit.
2. Nel progetto: `git -C tools/appunti-musica pull`, rigenerare con `./build-lilypond.sh` e controllare le differenze negli output.
3. Fare commit nel progetto del nuovo riferimento del sottomodulo insieme agli output rigenerati.

Una modifica allo script di build cambia l'impronta di tutti i sorgenti e quindi ricompila tutto. È voluto.
